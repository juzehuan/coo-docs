# -*- coding: utf-8 -*-
"""准备浏览器回归所需数据：为 COO-02(ENG) / COO-03(SAL) 创建并提交 pending_dept 版本。"""
import io
import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api"


def http(method, path, token=None, data=None, json_body=None, files=None):
    url = BASE + path
    body = None
    ct = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        ct = "application/json"
    elif files is not None:
        boundary = "----coo" + uuid.uuid4().hex
        buf = io.BytesIO()
        for fn, (fname, fbytes, ftype) in files:
            buf.write(f"--{boundary}\r\n".encode())
            buf.write(f'Content-Disposition: form-data; name="{fn}"; filename="{fname}"\r\n'.encode())
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
        ct = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url, data=body, method=method)
    if ct:
        req.add_header("Content-Type", ct)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def jget(method, path, token=None, json_body=None):
    st, body = http(method, path, token=token, json_body=json_body)
    try:
        return st, json.loads(body.decode("utf-8"))
    except Exception:
        return st, body.decode("utf-8", "replace")


st, data = jget("POST", "/auth/login", json_body={"username": "admin", "password": "admin123"})
tok = data["access_token"]
st, pkgs = jget("GET", "/packages", token=tok)
txt = b"browser regression prep\n"

for code in ("COO-02", "COO-03"):
    pkg = next(p for p in pkgs if p["code"] == code)
    st, ver = jget("POST", f"/packages/{pkg['id']}/versions", token=tok, json_body={"change_note": f"prep {code}"})
    vid = ver["id"]
    st, body = http("POST", f"/packages/{pkg['id']}/versions/{vid}/attachments", token=tok,
                    data={"order_no": "PREP", "batch_no": "P1"},
                    files=[("files", (f"prep_{code}.txt", txt, "text/plain"))])
    st, v = jget("POST", f"/packages/{pkg['id']}/versions/{vid}/submit", token=tok)
    print(f"{code}: version={ver.get('version_no')} status={v.get('status')} st={st}")
