# -*- coding: utf-8 -*-
"""回归测试：验证本轮 6 项修复的角色权限与数据隔离（仅用标准库）。
覆盖：N1 待办工厂隔离 / N2 订单 owner 隔离 / N3 审计导出角色 / N4 看板可见范围 / N5 导出日志 IP。
用法: python _regression_roles.py [BASE]
"""
import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api"

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


def http(method, path, token=None, data=None, json_body=None, files=None):
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
    admin = login("admin", "admin123")
    dept_eng = login("dept_eng", "dept123")
    coo = login("coo", "coo123")
    auditor = login("auditor", "audit123")
    eng_tok = login("submit_eng", "user123")
    fin_tok = login("submit_fin", "user123")

    _, users = jget("GET", "/org/users", token=admin)
    submit_eng = next(u for u in users if u["username"] == "submit_eng")["id"]
    submit_fin = next(u for u in users if u["username"] == "submit_fin")["id"]
    _, factories = jget("GET", "/factories", token=admin)
    rma = next(f for f in factories if f["code"] == "RMA")["id"]
    wev = next(f for f in factories if f["code"] == "WEV")["id"]
    _, pkgs = jget("GET", "/packages", token=admin)
    eng_pkg = next(p for p in pkgs if p["code"] == "COO-02")["id"]  # ENG 责任部门

    uniq = int(time.time() * 1000)

    print("== N2 订单可见性按 owner 隔离 ==")
    st, o1 = jget("POST", "/orders", token=admin, json_body={
        "order_no": f"OWN-ENG-{uniq}", "factory_id": rma, "customer": "T1", "product": "P",
        "quantity": 1, "export_date": "2026-12-31", "owner_user_id": submit_eng})
    chk("创建订单(owner=submit_eng)", st in (200, 201), f"st={st}")
    st, o2 = jget("POST", "/orders", token=admin, json_body={
        "order_no": f"OWN-FIN-{uniq}", "factory_id": rma, "customer": "T2", "product": "P",
        "quantity": 1, "export_date": "2026-12-31", "owner_user_id": submit_fin})
    chk("创建订单(owner=submit_fin)", st in (200, 201), f"st={st}")
    o1id, o2id = o1["id"], o2["id"]

    st, lst = jget("GET", "/orders", token=eng_tok)
    ids = [o["id"] for o in lst]
    chk("submit_eng 订单列表仅含本人订单", o1id in ids and o2id not in ids, f"可见数={len(ids)}")
    st, _ = jget("GET", f"/orders/{o2id}", token=eng_tok)
    chk("submit_eng 访问他人订单 -> 404/403", st in (404, 403), f"st={st}")
    st, lst = jget("GET", "/orders", token=fin_tok)
    ids = [o["id"] for o in lst]
    chk("submit_fin 订单列表仅含本人订单", o2id in ids and o1id not in ids, f"可见数={len(ids)}")
    st, _ = jget("GET", f"/orders/{o1id}", token=fin_tok)
    chk("submit_fin 访问他人订单 -> 404/403", st in (404, 403), f"st={st}")

    print("== N1 待办按工厂过滤 ==")
    st, wev_order = jget("POST", "/orders", token=admin, json_body={
        "order_no": f"WEV-{uniq}", "factory_id": wev, "customer": "WEV", "product": "P",
        "quantity": 1, "export_date": "2026-12-31"})
    chk("创建 WEV 订单", st in (200, 201), f"st={st}")
    st, op = jget("POST", f"/orders/{wev_order['id']}/packages", token=admin, json_body={"package_id": eng_pkg})
    chk("WEV 订单添加 ENG 资料包", st in (200, 201), f"st={st}")
    opid = op["id"]
    txt = b"regression isolation test\n"
    st, _hd, body = http(
        "POST", f"/orders/{wev_order['id']}/packages/{opid}/attachments", token=admin,
        data={"batch_no": "R1"}, files=[("files", ("iso.txt", txt, "text/plain"))])
    chk("WEV 订单实例上传附件", st == 200, f"st={st}")
    st, op = jget("POST", f"/orders/{wev_order['id']}/packages/{opid}/submit", token=admin)
    chk("WEV 订单实例提交 -> pending_dept", st == 200 and op.get("status") == "pending_dept", f"st={st}")
    st, todo = jget("GET", "/todo", token=dept_eng)
    wev_in = any(t.get("kind") == "order" and t.get("order_id") == wev_order["id"] for t in todo)
    chk("dept_eng(RMA) 待办不含 WEV 订单实例", not wev_in)
    # admin 可将 WEV 实例推进到 PENDING_COO（admin 具备部门级审核能力）
    st, op = jget("POST", f"/orders/{wev_order['id']}/packages/{opid}/review", token=admin,
                  json_body={"decision": "approve", "level": "dept", "reason": "ok"})
    chk("admin 部门级通过 WEV 实例 -> pending_coo", st == 200 and op.get("status") == "pending_coo", f"st={st}")
    st, todo_admin = jget("GET", "/todo", token=admin)
    wev_in_admin = any(t.get("kind") == "order" and t.get("order_id") == wev_order["id"] for t in todo_admin)
    chk("admin 待办包含 WEV 订单实例", wev_in_admin)

    print("== N4 看板完成度按可见范围 ==")
    st, dash = jget("GET", "/dashboard", token=eng_tok)
    chk("submit_eng 看板进度不含全量资料包", len(dash.get("package_progress", [])) == 0,
        f"n={len(dash.get('package_progress', []))}")
    st, dash_admin = jget("GET", "/dashboard", token=admin)
    chk("admin 看板进度含全部资料包", len(dash_admin.get("package_progress", [])) >= 18,
        f"n={len(dash_admin.get('package_progress', []))}")

    print("== N3 审计导出角色 + N5 导出日志 IP ==")
    st, _hd, _b = http("GET", "/audit/export", token=coo)
    chk("coo_reviewer 导出审计日志 -> 403", st == 403, f"st={st}")
    st, _hd, body = http("GET", "/audit/export", token=auditor)
    chk("auditor 导出审计日志 -> 200", st == 200, f"st={st}")
    csv_txt = body.decode("utf-8", "replace")
    chk("auditor 导出 CSV 含表头", "域" in csv_txt and "IP" in csv_txt)
    st, logs = jget("GET", "/audit/logs?domain=export", token=admin)
    exp = [l for l in logs if l.get("action") == "audit_csv"]
    chk("审计导出日志已记录", len(exp) >= 1, f"n={len(exp)}")
    chk("导出日志 IP 非空", bool(exp and exp[-1].get("ip")),
        f"ip={exp[-1].get('ip')!r}" if exp else "")
    st, _hd, _b = http("GET", "/audit/export", token=admin)
    chk("admin 导出审计日志 -> 200", st == 200, f"st={st}")

    print("")
    print(f"RESULT: PASS={PASS} FAIL={FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
