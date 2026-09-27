# -*- coding: utf-8 -*-
"""监听 x-hub 主窗 console 输出 N 秒，期间触发模式切换以复现编辑器挂载问题。"""
import json, time, importlib.util

spec = importlib.util.spec_from_file_location("cdpeval", r"D:\source\x-hub\scripts\cdp-eval.py")
cdp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cdp)

t = cdp.find_target()
ws = cdp.ws_connect(t)
cdp.send(ws, "Runtime.enable")

# 后台线程收事件简化：同步循环里先切换模式，再非阻塞读
cdp.send(ws, "Runtime.evaluate", {"expression":
  "(()=>{const f=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||x.textContent||'').trim()==='分屏预览'); if(f) f.click(); return 'to split';})()",
  "returnByValue": True})
time.sleep(2)
cdp.send(ws, "Runtime.evaluate", {"expression":
  "(()=>{const f=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||x.textContent||'').trim()==='实时预览'); if(f) f.click(); return 'to wysiwyg';})()",
  "returnByValue": True})

end = time.time() + 6
ws.settimeout(0.5)
while time.time() < end:
    try:
        msg = json.loads(ws.recv())
    except Exception:
        continue
    if msg.get("method") == "Runtime.consoleAPICalled":
        p = msg["params"]
        texts = [a.get("value", a.get("description", "")) for a in p.get("args", [])]
        print(f"[console.{p['type']}]", " | ".join(str(x)[:220] for x in texts))
    elif msg.get("method") == "Runtime.exceptionThrown":
        d = msg["params"]["exceptionDetails"]
        print("[EXC]", json.dumps(d, ensure_ascii=False)[:400])

# 最终状态
r = cdp.send(ws, "Runtime.evaluate", {"expression":
  "JSON.stringify({kids:document.querySelectorAll('.crepe-root *').length, prose:!!document.querySelector('.crepe-root .ProseMirror')})",
  "returnByValue": True})
print("STATE:", r.get("result", {}).get("result", {}).get("value"))
ws.close()
