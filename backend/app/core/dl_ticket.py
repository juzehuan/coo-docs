"""附件下载票据：短时效、单附件、绑定用户的一次性凭据。

为什么需要它:附件下载接口要求 `Authorization: Bearer`,而浏览器的原生下载
(`<a href>` 导航)带不了自定义头。前端因此改用 `fetch → res.blob() → 点击
object URL`,代价是**整个文件先在浏览器内存里缓冲完才落盘**:

- 无进度:实测 4Mbps 下载 40MB 附件,**85 秒内界面零反馈**,浏览器下载管理器
  也不显示——用户很可能以为没点上而反复点击,每次又重拉一遍;
- 无断点续传:服务端本就支持 Range(实测返回 206 + accept-ranges),但走 blob
  的路径用不上,连接一断就前功尽弃;
- 内存占用等于文件大小,工厂平板上连开几个大附件足以让页面崩掉。

改为:前端先用正常的 Bearer 请求换一张票据,再以普通导航带票据下载,交回浏览器
原生下载管理器(自带进度、暂停续传,且边下边写盘)。

票据的约束:HMAC 签名、**60 秒过期**、绑定到具体附件与具体用户,只用于下载这一
个用途。因此即便票据出现在 URL 里,可被利用的窗口极小、范围也仅限那一个附件;
请求日志只记录 `url.path`(不含查询串),不会把票据写进日志。
"""
import base64
import hashlib
import hmac
import json
import time

from app.core.runtime_secret import get_secret_key

TICKET_TTL_SECONDS = 60


def _sign(payload: bytes) -> str:
    sig = hmac.new(get_secret_key().encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue(attachment_id: int, user_id: int) -> str:
    """签发下载票据。"""
    payload = json.dumps(
        {"a": str(attachment_id), "u": str(user_id), "e": int(time.time()) + TICKET_TTL_SECONDS},
        separators=(",", ":"),
    ).encode()
    return f"{_b64(payload)}.{_sign(payload)}"


def verify(ticket: str, attachment_id: int) -> int | None:
    """校验票据并返回用户 ID；无效/过期/附件不匹配时返回 None。"""
    try:
        body, sig = ticket.split(".", 1)
        payload = _unb64(body)
        # compare_digest：避免签名比对的时序差异被用来逐字节试探
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        data = json.loads(payload)
        if int(data["e"]) < int(time.time()):
            return None
        if str(data["a"]) != str(attachment_id):
            return None
        return int(data["u"])
    except (ValueError, KeyError, TypeError):
        return None
