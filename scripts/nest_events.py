# -*- coding: utf-8 -*-
"""栈事件日志：打印模板区所有开闭事件与栈状态"""
import io
import re

path = r"src/components/NoteEditor.vue"
lines = io.open(path, encoding="utf-8").read().split("\n")
block = "\n".join(lines[2113:2515])
block = re.sub(r"<!--.*?-->", lambda m: "<!--" + " " * (len(m.group(0)) - 5) + "-->", block, flags=re.S)

VOID = {"input", "br", "img", "hr"}
stack = []


def line_of(pos):
    return 2114 + block.count("\n", 0, pos)


for m in re.finditer(r"<(/?)([A-Za-z][A-Za-z0-9-]*)((?:\"[^\"]*\"|'[^']*'|[^>])*?)(/?)>", block, re.S):
    closing, tag, attrs, sc = m.group(1), m.group(2), m.group(3), m.group(4)
    ln = line_of(m.start())
    if tag.lower() in VOID or sc == "/":
        continue
    if not closing:
        stack.append((tag, ln))
    else:
        names = [t for t, _ in stack]
        if tag not in names:
            print(f"L{ln}: </{tag}> 无匹配! 栈={stack}")
            continue
        idx = len(names) - 1 - names[::-1].index(tag)
        popped = stack[idx:]
        del stack[idx:]
        if len(popped) > 1:
            print(f"L{ln}: </{tag}> 隐式关闭 {[t for t, _ in popped[:-1]]}")
    if 2238 <= ln <= 2430 and tag in ("div", "template", "aside"):
        tag_c = "/" if closing else ""
        print(f"L{ln} <{tag_c}{tag}> 栈深{len(stack)}: {[t for t, _ in stack][-4:]}")
