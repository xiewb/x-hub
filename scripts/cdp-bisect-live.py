# -*- coding: utf-8 -*-
"""在真实 x-hub 应用内二分定位让 Crepe 挂载卡死的内容片段。"""
import json, time, importlib.util

spec = importlib.util.spec_from_file_location("cdpeval", r"D:\source\x-hub\scripts\cdp-eval.py")
cdp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cdp)

t = cdp.find_target()
ws = cdp.ws_connect(t)

def ev(expr):
    return cdp.evaluate(ws, expr)

def click_btn(label):
    return ev("(()=>{const f=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||x.textContent||'').trim()===%s); if(!f) return 'BTN_NOT_FOUND'; f.click(); return 'ok';})()" % json.dumps(label))

FRAGMENTS = {
  "h1-h4": "# 一级标题样式\n## 二级标题样式\n### 三级标题样式\n#### 四级标题样式\n",
  "inline": "正文段落一，包含**加粗**、*斜体*、`行内代码`、[链接](https://example.com)与==高亮==效果。\n",
  "blockquote": "> 引用块第一行\n> 引用块第二行\n",
  "ul": "- 无序列表项一\n- 无序列表项二\n",
  "ol": "1. 有序列表项一\n2. 有序列表项二\n",
  "tasklist": "- [ ] 任务项未完成\n- [x] 任务项已完成\n",
  "table": "| 列A | 列B |\n| --- | --- |\n| 甲 | 乙 |\n",
  "hr": "---\n",
  "codeblock": "```js\nconst a = 1;\n```\n",
}

# 打开测试笔记（当前应已在速记视图）
r = ev("(()=>{const it=[...document.querySelectorAll('.note-title')].find(x=>x.textContent.trim()==='ZZ样式对比测试'); if(!it) return 'NOT_FOUND'; it.click(); return 'ok';})()")
print("open note:", r)
time.sleep(2)

results = {}
for name, md in FRAGMENTS.items():
    # 1) 源码模式替换内容
    r = click_btn("源码")
    if r != "ok":
        results[name] = "src-btn-missing: " + str(r); continue
    time.sleep(1.2)
    r = ev("(()=>{const cm=document.querySelector('.cm-content'); if(!cm) return 'NO_CM'; cm.focus(); document.execCommand('selectAll',false,null); const ok=document.execCommand('insertText',false,%s); return 'inserted:'+ok;})()" % json.dumps(md))
    if not str(r).startswith("inserted:true"):
        results[name] = "insert-fail: " + str(r); continue
    time.sleep(1.5)  # 防抖保存
    # 2) 切实时预览测挂载
    r = click_btn("实时预览")
    if r != "ok":
        results[name] = "wys-btn-missing"; continue
    time.sleep(2.5)
    state = json.loads(ev("JSON.stringify({kids:document.querySelectorAll('.crepe-root *').length, prose:!!document.querySelector('.crepe-root .ProseMirror'), h1:document.querySelectorAll('.crepe-root h1').length, li:document.querySelectorAll('.crepe-root li').length, tb:document.querySelectorAll('.crepe-root table').length, pre:document.querySelectorAll('.crepe-root pre').length})"))
    ok = state.get("prose") and state.get("kids", 0) > 5
    results[name] = ("PASS " + json.dumps(state)) if ok else ("FAIL " + json.dumps(state))
    print(f"[{name}] {results[name]}")

print("\n==== 汇总 ====")
for k, v in results.items():
    if not v.startswith("PASS"):
        print("❌", k, "->", v[:160])
ws.close()
