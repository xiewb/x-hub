# -*- coding: utf-8 -*-
"""采样 x-hub 笔记编辑器（Crepe）与预览（marked）两侧的计算样式并对比。
用法: python cdp-style-diff.py [crepe|preview]"""
import json, sys, importlib.util

spec = importlib.util.spec_from_file_location("cdpeval", r"D:\source\x-hub\scripts\cdp-eval.py")
cdp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cdp)

SAMPLE_JS = r"""
(() => {
  const PROPS = ['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing',
    'marginTop','marginBottom','paddingTop','paddingBottom','paddingLeft',
    'color','backgroundColor','borderLeftWidth','borderLeftColor','borderTopWidth','borderBottomWidth',
    'listStyleType','textDecorationLine','display'];
  const rootSel = __SIDE__ === 'crepe' ? '.crepe-root .ProseMirror' : '.md-preview';
  const root = document.querySelector(rootSel);
  if (!root) return JSON.stringify({error: 'root not found: ' + rootSel});
  const out = {};
  const els = root.querySelectorAll('h1,h2,h3,h4,p,ul,ol,li,blockquote,hr,code,pre,strong,em,a,td,th');
  const seen = new Set();
  for (const el of els) {
    let key = el.tagName.toLowerCase();
    // 行内 code 与代码块内 code 区分
    if (key === 'code' && el.closest('pre')) key = 'pre>code';
    if (seen.has(key)) continue;
    seen.add(key);
    const cs = getComputedStyle(el);
    const rec = {};
    for (const p of PROPS) rec[p] = cs[p];
    // 家族字体只留第一个
    rec.fontFamily = rec.fontFamily.split(',')[0].replace(/"/g, '').slice(0, 24);
    out[key] = rec;
    if (out._count === undefined) out._count = 0;
    out._count++;
  }
  // 容器本身
  const cs = getComputedStyle(root);
  out._container = {fontFamily: cs.fontFamily.split(',')[0].replace(/"/g,'').slice(0,24),
    fontSize: cs.fontSize, lineHeight: cs.lineHeight, color: cs.color};
  return JSON.stringify(out);
})();
"""

side = sys.argv[1] if len(sys.argv) > 1 else "crepe"
js = SAMPLE_JS.replace("__SIDE__", repr(side))

t = cdp.find_target()
ws = cdp.ws_connect(t) if hasattr(cdp, 'ws_connect') else __import__('websocket').create_connection(t['webSocketDebuggerUrl'], timeout=20, suppress_origin=True)
out = cdp.evaluate(ws, js)
ws.close()
print(json.dumps(json.loads(out), ensure_ascii=False, indent=1))
