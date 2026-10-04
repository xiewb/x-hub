#!/usr/bin/env python3
"""监听 CDP console/log 3 秒，抓 CSP 等报错；期间可选执行一段 JS。
用法: python scripts/cdp-console2.py ["<js to eval>"]
"""
import json, sys, time, urllib.request
import websocket

def find_target():
    ts = json.load(urllib.request.urlopen('http://127.0.0.1:9222/json'))
    for t in ts:
        if t['type'] == 'page' and '主窗' in t['title']:
            return t
    raise SystemExit('主窗未找到')

def main():
    t = find_target()
    ws = websocket.create_connection(t['webSocketDebuggerUrl'], timeout=10, suppress_origin=True)
    mid = 0
    def cmd(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        return mid
    cmd("Runtime.enable")
    cmd("Log.enable")
    cmd("Security.enable")
    if len(sys.argv) > 1:
        time.sleep(0.3)
        cmd("Runtime.evaluate", {"expression": sys.argv[1]})
    msgs = []
    deadline = time.time() + 4
    while time.time() < deadline:
        try:
            ws.settimeout(max(0.2, deadline - time.time()))
            m = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            break
        except Exception:
            break
        meth = m.get("method", "")
        if meth == "Runtime.consoleAPICalled":
            args = m["params"].get("args", [])
            text = " ".join(str(a.get("value", a.get("description", "")))[:200] for a in args)
            msgs.append(f"[console.{m['params']['type']}] {text[:300]}")
        elif meth == "Log.entryAdded":
            e = m["params"]["entry"]
            msgs.append(f"[log.{e.get('level')}] {e.get('text','')[:300]}")
        elif meth == "Security.securityStateChanged":
            pass
    print("\n".join(msgs[-40:]) if msgs else "(no console/log output)")

if __name__ == "__main__":
    main()
