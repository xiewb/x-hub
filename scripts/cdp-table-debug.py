# -*- coding: utf-8 -*-
"""复现表格挂载卡死并抓取所有异常/unhandledrejection/console。"""
import json, time, importlib.util

spec = importlib.util.spec_from_file_location("cdpeval", r"D:\source\x-hub\scripts\cdp-eval.py")
cdp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cdp)

t = cdp.find_target()
ws = cdp.ws_connect(t)
cdp.send(ws, "Runtime.enable")

def ev(expr):
    return cdp.evaluate(ws, expr)

# 注入全局监听
ev("""
(()=>{ if (window.__dbgInstalled) return 'already';
  window.__dbg = [];
  window.addEventListener('unhandledrejection', e => window.__dbg.push(['REJ', String(e.reason).slice(0,300)]));
  window.addEventListener('error', e => window.__dbg.push(['ERR', e.message, e.filename+':'+e.lineno]));
  const origError = console.error;
  console.error = (...a) => { window.__dbg.push(['console.error', a.map(x=>String(x).slice(0,200)).join(' | ')]); origError(...a); };
  window.__dbgInstalled = true; return 'installed';
})()
""")

# 打开测试笔记
ev("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='速记'); if(b) b.click(); return 'ok';})()")
time.sleep(1.5)
ev("(()=>{const it=[...document.querySelectorAll('.note-title')].find(x=>x.textContent.trim()==='ZZ样式对比测试'); if(!it) return 'NOT_FOUND'; it.click(); return 'ok';})()")
time.sleep(2)

# 源码模式写表格
ev("(()=>{const f=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||x.textContent||'').trim()==='源码'); if(f) f.click(); return 'ok';})()")
time.sleep(1.2)
r = ev("(()=>{const cm=document.querySelector('.cm-content'); if(!cm) return 'NO_CM'; cm.focus(); document.execCommand('selectAll',false,null); return 'sel:'+document.execCommand('insertText',false,'| 列A | 列B |\\n| --- | --- |\\n| 甲 | 乙 |\\n');})()")
print("insert:", r)
time.sleep(1.5)

# 切实时预览复现
ev("(()=>{const f=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||x.textContent||'').trim()==='实时预览'); if(f) f.click(); return 'ok';})()")

# 收集 8 秒内的事件
end = time.time() + 8
ws.settimeout(0.5)
while time.time() < end:
    try:
        msg = json.loads(ws.recv())
    except Exception:
        continue
    if msg.get("method") == "Runtime.consoleAPICalled":
        p = msg["params"]
        texts = [a.get("value", a.get("description", "")) for a in p.get("args", [])]
        print("[console.%s]" % p["type"], " | ".join(str(x)[:260] for x in texts))
    elif msg.get("method") == "Runtime.exceptionThrown":
        d = msg["params"]["exceptionDetails"]
        print("[EXC]", json.dumps(d, ensure_ascii=False)[:500])

print("window.__dbg:", ev("JSON.stringify(window.__dbg||[])"))
print("state:", ev("JSON.stringify({kids:document.querySelectorAll('.crepe-root *').length})"))
ws.close()
