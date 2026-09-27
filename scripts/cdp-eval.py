# -*- coding: utf-8 -*-
"""通过 CDP 对 x-hub 主窗口执行 JS。用法: python cdp-eval.py "<js>" [--target 主窗|id前缀]"""
import json, sys, urllib.request, websocket

TARGET_NAME = "主窗"

def find_target():
    data = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json"))
    for t in data:
        if t.get("type") == "page" and t.get("title", "").startswith("x-hub " + TARGET_NAME):
            return t
    for t in data:
        if t.get("type") == "page" and "tauri.localhost" in t.get("url", "") and "chrome/notice/ball" not in t.get("url", ""):
            return t
    raise SystemExit("target not found")

def evaluate(ws, expr):
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True,
                                   "awaitPromise": True, "userGesture": True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == 1:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                return {"__error__": r["exceptionDetails"].get("exception", {}).get("description", str(r["exceptionDetails"]))}
            return r.get("result", {}).get("value")

def ws_connect(t):
    return websocket.create_connection(t["webSocketDebuggerUrl"], timeout=20, suppress_origin=True)

def send(ws, method, params=None):
    ws.send(json.dumps({"id": 2, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == 2:
            return msg

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "document.title"
    t = find_target()
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=20, suppress_origin=True)
    out = evaluate(ws, arg)
    ws.close()
    if isinstance(out, str):
        print(out)
    else:
        print(json.dumps(out, ensure_ascii=False, indent=1))
