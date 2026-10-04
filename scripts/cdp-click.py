#!/usr/bin/env python3
"""CDP 真实输入点击：用 Input.dispatchMouseEvent 走浏览器输入管线，等价真实鼠标点击。
用法: python scripts/cdp-click.py "<css_selector>"
"""
import json, sys, time, urllib.request
import websocket

def find_target():
    ts = json.load(urllib.request.urlopen('http://127.0.0.1:9222/json'))
    for t in ts:
        if t['type']=='page' and '主窗' in t['title']:
            return t
    raise SystemExit('主窗 target 未找到')

def main():
    selector = sys.argv[1] if len(sys.argv) > 1 else '.te-btn--primary'
    t = find_target()
    ws = websocket.create_connection(t['webSocketDebuggerUrl'], timeout=20, suppress_origin=True)
    # 1) 取按钮坐标
    js = f"""(function(){{
      const el=document.querySelector('{selector}');
      if(!el) return null;
      const r=el.getBoundingClientRect();
      return JSON.stringify({{x:r.left+r.width/2, y:r.top+r.height/2, disabled:el.disabled}});
    }})()"""
    ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":js,"returnByValue":True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id")==1:
            val = m["result"]["result"].get("value")
            break
    if not val:
        print("element not found"); return
    pos = json.loads(val)
    print(f"target {selector} @ ({pos['x']:.0f},{pos['y']:.0f}) disabled={pos['disabled']}")
    # 2) 真实鼠标事件序列
    mid = 10
    def cmd(method, params):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({"id":mid,"method":method,"params":params}))
    x, y = pos['x'], pos['y']
    cmd("Input.dispatchMouseEvent", {"type":"mouseMoved","x":x,"y":y,"button":"none","pointerType":"mouse"})
    time.sleep(0.05)
    cmd("Input.dispatchMouseEvent", {"type":"mousePressed","x":x,"y":y,"button":"left","buttons":1,"clickCount":1,"pointerType":"mouse"})
    time.sleep(0.06)
    cmd("Input.dispatchMouseEvent", {"type":"mouseReleased","x":x,"y":y,"button":"left","buttons":0,"clickCount":1,"pointerType":"mouse"})
    time.sleep(0.5)
    print("real click dispatched")

if __name__ == "__main__":
    main()
