# -*- coding: utf-8 -*-
"""验证 submitter 角色端到端可用性（临时脚本，审查后删除）。"""
import json
import urllib.request
import urllib.error
import time

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api"
# admin 密码可经环境变量覆盖（生产已轮换，不再是 admin123）
ADMIN_PWD = os.environ.get("COO_ADMIN_PWD", "admin123")


def http(method, path, token=None, json_body=None):
    url = BASE + path
    body = json.dumps(json_body).encode() if json_body is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    if json_body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode() or "{}")
    except Exception as e:
        return 0, str(e)


def login(u, p):
    st, d = http("POST", "/auth/login", json_body={"username": u, "password": p})
    assert st == 200, (st, d)
    return d["access_token"]


def main():
    sub = login("submit_eng", "user123")
    admin = login("admin", ADMIN_PWD)

    print("== 1. submitter 可见资料包 ==")
    st, pkgs = http("GET", "/packages", token=sub)
    print(f"  /packages -> {st}, visible={len(pkgs)}")
    if pkgs:
        print("  first:", pkgs[0].get("code"), "editable=", pkgs[0].get("editable"))

    print("== 2. submitter 待办 ==")
    st, todos = http("GET", "/todo", token=sub)
    print(f"  /todo -> {st}, count={len(todos)}")

    print("== 3. submitter 建单并添加资料包 ==")
    st, fs = http("GET", "/factories", token=sub)
    fac = fs[0]["id"]
    uniq = int(time.time() * 1000)
    st, order = http("POST", "/orders", token=sub,
                     json_body={"order_no": f"SUB-{uniq}", "factory_id": fac,
                                "customer": "Sub Test", "product": "X", "quantity": 1})
    print(f"  create order -> {st}")
    oid = order.get("id")
    st, pkgs2 = http("GET", "/packages", token=sub)
    pid = None
    if pkgs2:
        pid = pkgs2[0]["id"]
    st, op = http("POST", f"/orders/{oid}/packages", token=sub, json_body={"package_id": pid})
    print(f"  add order package -> {st}, owner_user_id={op.get('owner_user_id')}, status={op.get('status')}")
    opid = op.get("id")
    print(f"  submitter id vs owner: sub={sub and 'N/A'}, op.owner={op.get('owner_user_id')}")

    print("== 4. submitter 上传附件（应期望 200） ==")
    # multipart upload
    import io, uuid
    boundary = "----coo" + uuid.uuid4().hex
    txt = b"submitter test file content"
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="files"; filename="sub.txt"\r\n')
    body.write(b"Content-Type: text/plain\r\n\r\n")
    body.write(txt)
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        BASE + f"/orders/{oid}/packages/{opid}/attachments",
        data=body.getvalue(), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Authorization", f"Bearer {sub}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"  upload -> {r.status}")
    except urllib.error.HTTPError as e:
        print(f"  upload -> {e.code} {e.read().decode()[:200]}")

    print("== 5. 测试结束后清理订单（admin） ==")
    st, _ = http("DELETE", f"/orders/{oid}", token=admin)
    print(f"  cleanup -> {st}")


if __name__ == "__main__":
    main()
