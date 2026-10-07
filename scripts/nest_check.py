# -*- coding: utf-8 -*-
"""多行感知的模板栈解析：找出根 div 被提前闭合/嵌套异常的位置"""
import io
import re

path = r"src/components/NoteEditor.vue"
lines = io.open(path, encoding="utf-8").read().split("\n")
block = "\n".join(lines[2113:2515])  # <template> .. 含最终 </template> 前的最后一行

# 去注释（保留位置占位）
def strip_comments(text):
    return re.sub(r"<!--.*?-->", lambda m: "<!--" + " " * (len(m.group(0)) - 5) + "-->", text, flags=re.S)

block = strip_comments(block)

VOID = {"input", "br", "img", "hr", "kbd"}  # kbd 非空元素，移除
VOID = {"input", "br", "img", "hr"}
P_LIKE = {"p"}

stack = []  # (tag, file_line, col)
tag_iter = re.finditer(r"<(/?)([A-Za-z][A-Za-z0-9-]*)((?:\"[^\"]*\"|'[^']*'|[^>])*?)(/?)>", block, re.S)


def line_of(pos):
    return 2114 + block.count("\n", 0, pos)


for m in tag_iter:
    closing, tag, attrs, sc = m.group(1), m.group(2), m.group(3), m.group(4)
    ln = line_of(m.start())
    if tag.lower() in VOID or sc == "/":
        continue
    if not closing:
        stack.append((tag, ln))
    else:
        # 找栈中最近的同名
        names = [t for t, _ in stack]
        if tag not in names:
            print(f"L{ln}: </{tag}> 无匹配开标签! 栈: {stack[-4:]}")
            continue
        idx = len(names) - 1 - names[::-1].index(tag)
        popped = stack[idx:]
        del stack[idx:]
        if len(popped) > 1:
            print(f"L{ln}: </{tag}> 隐式关闭了 {[(t, l) for t, l in popped[:-1]]}")
        if tag == "div" and len(stack) == 1 and stack[0][0] == "template":
            print(f"L{ln}: *** 根 div 在此被关闭! ***")
print("剩余未闭合:", [(t, l) for t, l in stack])
