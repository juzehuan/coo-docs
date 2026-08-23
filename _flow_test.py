# -*- coding: utf-8 -*-
"""COO 资料收集平台 端到端流程测试（仅用标准库）。
覆盖：登录 / 订单 / 资料包 / 上传 / 下载 / 预览 / 审核闭环 / 受控区 / NAS / 角色隔离。
用法: python _flow_test.py [BASE]
"""
import io
import json
import os
import sys
import tempfile
import urllib.request
import urllib.parse
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api"
# admin 密码可经环境变量覆盖（生产已轮换，不再是 admin123）
ADMIN_PWD = os.environ.get("COO_ADMIN_PWD", "admin123")

PASS = 0
FAIL = 0


def chk(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name} {extra}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def header_of(hd, key):
    """大小写不敏感地从响应头 dict 取值。"""
    low = key.lower()
    for k, v in hd.items():
        if k.lower() == low:
            return v
    return None


def http(method, path, token=None, data=None, json_body=None, files=None, raw=False):
    """发送请求，返回 (status, headers, body_bytes)。
    files: list[(field_name, (fname, fbytes, ftype)), ...]，支持同名字段多文件。
    """
    url = BASE + path
    body = None
    content_type = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        content_type = "application/json"
    elif files is not None:
        boundary = "----coo" + uuid.uuid4().hex
        buf = io.BytesIO()
        for field_name, (fname, fbytes, ftype) in files:
            buf.write(f"--{boundary}\r\n".encode())
            buf.write(f'Content-Disposition: form-data; name="{field_name}"; filename="{fname}"\r\n'.encode())
            buf.write(f"Content-Type: {ftype}\r\n\r\n".encode())
            buf.write(fbytes)
            buf.write(b"\r\n")
        for name, value in data.items():
            buf.write(f"--{boundary}\r\n".encode())
            buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            buf.write(value.encode("utf-8"))
            buf.write(b"\r\n")
        buf.write(f"--{boundary}--\r\n".encode())
        body = buf.getvalue()
        content_type = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url, data=body, method=method)
    if content_type:
        req.add_header("Content-Type", content_type)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:  # noqa
        return 0, {}, str(e).encode()


def jget(method, path, token=None, json_body=None):
    st, hd, body = http(method, path, token=token, json_body=json_body)
    try:
        return st, json.loads(body.decode("utf-8"))
    except Exception:
        return st, body.decode("utf-8", "replace")


def login(user, pwd):
    st, data = jget("POST", "/auth/login", json_body={"username": user, "password": pwd})
    assert st == 200 and data.get("access_token"), f"login {user} failed: {st} {data}"
    return data["access_token"]


def main():
    tmpdir = tempfile.mkdtemp(prefix="coo_flow_")
    txt_bytes = "COO test note 001 - RMA original certificate\n".encode("utf-8")
    pdf_bytes = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF"
    )

    print("== ORDER FLOW ==")
    admin = login("admin", ADMIN_PWD)
    ah = {"Authorization": admin}

    # 创建专用测试订单（幂等：用唯一订单号）
    import time
    st, factories = jget("GET", "/factories", token=admin)
    chk("list factories 200", st == 200)
    fac = factories[0]
    uniq = int(time.time() * 1000)
    st, order = jget("POST", "/orders", token=admin,
                     json_body={"order_no": f"FLOW-{uniq}", "factory_id": fac["id"],
                                "customer": "Flow Test", "product": "Golf Buggy",
                                "quantity": 10, "export_date": "2026-12-31"})
    chk("create test order (200/201)", st in (200, 201), f"st={st} {order}")
    oid = order["id"]
    order_no = order.get("order_no", "?")
    print(f"  order id={oid} no={order_no}")

    st, pkgs = jget("GET", "/packages", token=admin)
    chk("list packages 200", st == 200)
    # COO-02 责任部门 ENG，与种子部门审核人 dept_eng 匹配，可走完整两级审核
    pkg = next(p for p in pkgs if p.get("code") == "COO-02")
    pid = pkg["id"]

    st, detail = jget("GET", f"/orders/{oid}", token=admin)
    chk("order detail 200", st == 200)
    op = next((x for x in detail.get("packages", []) if x.get("package_id") == pid), None)
    if op is None:
        st, op = jget("POST", f"/orders/{oid}/packages", token=admin, json_body={"package_id": pid})
        chk("create order package (200/201)", st in (200, 201), f"st={st}")
    opid = op["id"]
    print(f"  op id={opid}")

    # 上传附件（txt + pdf）
    st, _hd, body = http(
        "POST", f"/orders/{oid}/packages/{opid}/attachments",
        token=admin,
        data={"batch_no": "TEST-B1"},
        files=[
            ("files", ("coo_test_notes.txt", txt_bytes, "text/plain")),
            ("files", ("coo_test_doc.pdf", pdf_bytes, "application/pdf")),
        ],
    )
    atts = json.loads(body.decode("utf-8")) if st == 200 else []
    chk("upload returns 2 attachments", st == 200 and len(atts) == 2, f"st={st}")
    txt_att = next(a for a in atts if a["original_name"].endswith(".txt"))
    pdf_att = next(a for a in atts if a["original_name"].endswith(".pdf"))
    print(f"  txt={txt_att['id']} pdf={pdf_att['id']}")

    # 下载（带 token）
    st, hd, body = http("GET", f"/orders/{oid}/packages/{opid}/attachments/{txt_att['id']}/file", token=admin)
    chk("download txt 200", st == 200)
    chk("download content matches", b"COO test note" in body)

    # 预览（pdf, preview=true）
    st, hd, body = http("GET", f"/orders/{oid}/packages/{opid}/attachments/{pdf_att['id']}/file?preview=true", token=admin)
    chk("preview pdf 200", st == 200)
    chk("preview content-type pdf", "pdf" in (header_of(hd, "Content-Type") or "").lower(), header_of(hd, "Content-Type"))

    # 导出 CSV（带 token）
    st, hd, body = http("GET", f"/orders/{oid}/export", token=admin)
    chk("export csv with token 200", st == 200)
    chk("export csv has header", "工厂" in body.decode("utf-8", "replace") or "order" in body.decode("utf-8", "replace").lower())

    # 导出 CSV（不带 token）-> 预期 401
    st, _, _ = http("GET", f"/orders/{oid}/export")
    chk("export csv WITHOUT token -> 401", st == 401, f"st={st}")

    # 导出 ZIP（带 token）
    st, hd, body = http("GET", f"/orders/{oid}/export/zip", token=admin)
    chk("export zip with token 200", st == 200)
    chk("zip content-type zip", "zip" in (header_of(hd, "Content-Type") or "").lower(), header_of(hd, "Content-Type"))
    chk("zip is real zip (PK header)", body[:2] == b"PK")

    # 提交 + 两级审核闭环
    st, op = jget("POST", f"/orders/{oid}/packages/{opid}/submit", token=admin)
    chk("order submit -> pending_dept", st == 200 and op.get("status") == "pending_dept", f"st={st} {op}")

    dept = login("dept_eng", "dept123")
    st, op = jget("POST", f"/orders/{oid}/packages/{opid}/review", token=dept,
                  json_body={"decision": "approve", "level": "dept", "reason": "ok"})
    chk("dept approve -> pending_coo", st == 200 and op.get("status") == "pending_coo", f"st={st} {op}")

    coo = login("coo", "coo123")
    st, op = jget("POST", f"/orders/{oid}/packages/{opid}/review", token=coo,
                  json_body={"decision": "approve", "level": "coo", "reason": "ok"})
    chk("coo approve -> released+locked", st == 200 and op.get("status") == "released" and op.get("locked") is True, f"st={st} {op}")

    # 已放行不可删除
    st, _ = jget("DELETE", f"/orders/{oid}/packages/{opid}", token=admin)
    chk("released op cannot be removed (4xx)", st >= 400, f"st={st}")

    print("== NAS SYNC ==")
    st, sync = jget("POST", "/nas/sync", token=coo)
    chk("nas sync runs", st == 200 and sync.get("status") in ("success", "partial"), f"st={st} {sync}")
    st, stat = jget("GET", "/nas/status", token=admin)
    chk("nas status 200", st == 200)
    st, re_det = jget("GET", f"/orders/{oid}", token=admin)
    op_now = next(x for x in re_det.get("packages", []) if x.get("id") == opid)
    unsynced = [a for a in op_now.get("attachments", []) if a.get("nas_synced") is not True]
    chk("order attachments synced to NAS", not unsynced, f"unsynced={len(unsynced)}")

    print("== PACKAGE FLOW ==")
    st, ver = jget("POST", f"/packages/{pid}/versions", token=admin, json_body={"change_note": "test"})
    chk("create version draft (200/201)", st in (200, 201) and ver.get("version_no", "").startswith("V") and ver.get("status") == "draft", f"st={st} ver={ver.get('version_no')}")
    vid = ver["id"]
    st, _hd, patts_body = http(
        "POST", f"/packages/{pid}/versions/{vid}/attachments",
        token=admin,
        data={"order_no": "ORD-T", "batch_no": "B1"},
        files=[("files", ("coo_test_doc.pdf", pdf_bytes, "application/pdf"))],
    )
    patts = json.loads(patts_body.decode("utf-8")) if st == 200 else []
    chk("package upload attachment", st == 200 and len(patts) == 1, f"st={st}")
    st, v = jget("POST", f"/packages/{pid}/versions/{vid}/submit", token=admin)
    chk("package submit -> pending_dept", st == 200 and v.get("status") == "pending_dept", f"st={st} {v}")
    st, v = jget("POST", f"/packages/{pid}/versions/{vid}/review", token=dept,
                 json_body={"decision": "approve", "level": "dept", "reason": "ok"})
    chk("package dept approve -> pending_coo", st == 200 and v.get("status") == "pending_coo", f"st={st} {v}")
    st, v = jget("POST", f"/packages/{pid}/versions/{vid}/review", token=coo,
                 json_body={"decision": "approve", "level": "coo", "reason": "ok"})
    chk("package coo approve -> released+locked", st == 200 and v.get("status") == "released" and v.get("locked") is True, f"st={st} {v}")

    # 受控区可见 + ZIP 下载
    st, ctl = jget("GET", "/controlled", token=admin)
    chk("controlled 200", st == 200)
    visible = [c for c in ctl if c.get("package_code") == "COO-02" and c.get("version", {}).get("id") == vid]
    chk("controlled shows released package", len(visible) > 0)
    st, hd, body = http("GET", f"/controlled/{pid}/versions/{vid}/export/zip", token=admin)
    chk("controlled zip download 200", st == 200)
    chk("controlled zip PK header", body[:2] == b"PK")

    print("== ROLE ISOLATION ==")
    auditor = login("auditor", "audit123")
    st, _ = jget("POST", "/nas/sync", token=auditor)
    chk("auditor cannot trigger NAS sync (403)", st == 403, f"st={st}")

    print("")
    print(f"RESULT: PASS={PASS} FAIL={FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
