"""MinIO/S3 对象存储客户端（NAS 归档后端）。

对齐落地方案「5.2 推荐方案：S3 兼容接口」：
- 用 boto3 通过 S3 协议访问 NAS 对象存储（MinIO / 群晖 / 威联通 / 云对象存储）；
- 对象键沿用受控目录规范：{NAS_BASE_DIRNAME}/{项目}/{资料包}_{简称}/{版本号}/{原文件名}。
未配置 S3（S3_ENDPOINT_URL 为空）时返回禁用状态，nas_sync 自动退化为本地目录模式。
"""
import logging

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings  # noqa: F401  （保留：其它常量仍用）
from app.core import nas_config

logger = logging.getLogger(__name__)

# 单部分上传时 MinIO/S3 返回的 ETag 即内容 MD5；阈值需大于 MAX_FILE_MB，
# 否则 boto3 对超阈值文件走分片上传，ETag 变为分片哈希，无法用 MD5 校验
ETAG_IS_MD5 = True


def enabled() -> bool:
    """是否启用 S3 后端：以数据库中的运行时配置为准（管理员可在界面修改）。"""
    return nas_config.s3_enabled()


def bucket() -> str:
    return nas_config.get_config()["bucket"]


def client():
    """构建 S3 客户端；未启用时返回 None（每次新建，客户端无连接池副作用）。"""
    if not enabled():
        return None
    cfg = nas_config.get_config()
    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint_url"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name=cfg["region"] or None,
        use_ssl=cfg["use_ssl"],
        config=BotoConfig(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def ensure_bucket(cli=None, retries: int = 3) -> bool:
    """确保存储桶存在；成功返回 True。"""
    if not enabled():
        return False
    cli = cli or client()
    for i in range(retries):
        try:
            try:
                cli.head_bucket(Bucket=bucket())
                return True
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("404", "NoSuchBucket", "NotFound"):
                    cli.create_bucket(Bucket=bucket())
                    return True
                raise
        except (BotoCoreError, ClientError) as e:  # noqa: BLE001
            logger.warning("S3 ensure_bucket retry %s/%s: %s", i + 1, retries, e)
    return False


def reachable(cli=None) -> bool:
    """探测 S3 是否可达（能列出桶）。"""
    if not enabled():
        return False
    try:
        (cli or client()).list_buckets()
        return True
    except Exception:  # noqa: BLE001
        return False


def put_file(cli, key: str, local_path: str) -> bool:
    """上传本地文件到对象；返回是否成功。

    强制单部分上传（阈值 = MAX_FILE_MB + 1），保证 ETag 即文件 MD5，
    便于 nas_sync 用 MD5 校验同步完整性。
    """
    try:
        cfg = TransferConfig(multipart_threshold=settings.MAX_FILE_MB * 1024 * 1024 + 1)
        cli.upload_file(local_path, bucket(), key, Config=cfg)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("S3 put_file %s failed: %s", key, e)
        return False


def put_bytes(cli, key: str, data: bytes, content_type: str = "text/plain") -> bool:
    try:
        cli.put_object(Bucket=bucket(), Key=key, Body=data, ContentType=content_type)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("S3 put_bytes %s failed: %s", key, e)
        return False


def head(cli, key: str) -> dict | None:
    """返回对象元数据（ContentLength/ETag），不存在返回 None。"""
    try:
        return cli.head_object(Bucket=bucket(), Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code", "") in ("404", "NoSuchKey"):
            return None
        raise
    except BotoCoreError:
        return None


def delete(cli, key: str) -> None:
    try:
        cli.delete_object(Bucket=bucket(), Key=key)
    except Exception:  # noqa: BLE001
        logger.warning("S3 delete %s failed", key)


def list_keys(cli, prefix: str = "") -> list[str]:
    """列出桶内对象键（用于验证/管理，limit 由分页保护）。"""
    try:
        paginator = cli.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=bucket(), Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys
    except Exception:  # noqa: BLE001
        return []
