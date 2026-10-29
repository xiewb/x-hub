import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  expandBlankLines,
  cleanupEditorPlaceholderLines,
  dropEmptyListMarkerLines,
} from '../src/utils/markdownLines.ts'

// 模拟序列化→保存→再装载的完整往返
const roundTrip = (src) => cleanupEditorPlaceholderLines(expandBlankLines(src))

test('m 个连续空行 ⇔ m−1 个空段落：展开', () => {
  assert.equal(expandBlankLines('A\n\n\nB'), 'A\n\n\u200B\n\nB')
  assert.equal(expandBlankLines('A\n\n\n\n\nB'), 'A\n\n\u200B\n\n\u200B\n\n\u200B\n\nB')
})

test('单个空行（标准段落分隔）不展开', () => {
  assert.equal(expandBlankLines('A\n\nB'), 'A\n\nB')
  assert.equal(expandBlankLines('A\nB'), 'A\nB')
})

test('围栏与公式里的空行是正文，不展开', () => {
  assert.equal(expandBlankLines('```\na\n\n\nb\n```\n\n\n后文'), '```\na\n\n\nb\n```\n\n\u200B\n\n后文')
  assert.equal(expandBlankLines('$$\na\n\n\nb\n$$\n\n\n后文'), '$$\na\n\n\nb\n$$\n\n\u200B\n\n后文')
})

test('回收：序列化形态「段\\n\\n占位\\n\\n段」→ 空行数 = 空段落数', () => {
  assert.equal(cleanupEditorPlaceholderLines('A\n\n\u200B\n\nB'), 'A\n\n\nB')
  assert.equal(cleanupEditorPlaceholderLines('A\n\n\u200B\n\n\u200B\n\n\u200B\n\nB'), 'A\n\n\n\n\nB')
})

test('回收：文末占位行清成真空行（维持旧版行为）', () => {
  assert.equal(cleanupEditorPlaceholderLines('A\n\n\u200B'), 'A\n\n')
  assert.equal(cleanupEditorPlaceholderLines('A\u200B'), 'A')
})

test('往返不漂移：expand → 回收 → expand 是不动点', () => {
  for (const src of [
    'A\n\nB',
    'A\n\n\nB',
    'A\n\n\n\n\nB',
    '# 标题\n\n\n\n- 列表\n- 项目\n\n\n\n尾段',
    'A\n\n\n```js\nx\n\n\ny\n```\n\nB',
    'A\n\n\n',
  ]) {
    const once = roundTrip(src)
    assert.equal(roundTrip(once), once, `往返漂移: ${JSON.stringify(src)}`)
  }
})

test('往返还原：干净源码经一轮往返后空行数不变', () => {
  for (const src of ['A\n\nB', 'A\n\n\nB', 'A\n\n\n\n\nB', 'A\n\n\n']) {
    assert.equal(roundTrip(src), src, `空行数被改变: ${JSON.stringify(src)}`)
  }
})

test('空列表项伪行：只清普通行，围栏内的 1\\. 保留', () => {
  assert.equal(dropEmptyListMarkerLines('甲\n1\\.\n乙\n- \n丙'), '甲\n\n乙\n\n丙')
  assert.equal(dropEmptyListMarkerLines('```\n1\\.\n- \n```\n尾'), '```\n1\\.\n- \n```\n尾')
})

test('expandBlankLines 幂等：展开结果再展开不变', () => {
  for (const src of ['A\n\n\nB', 'A\n\n\n\n\nB', 'A\n\nB']) {
    assert.equal(expandBlankLines(expandBlankLines(src)), expandBlankLines(src))
  }
})

test('NBSP 空段落在回收时同样并入空行', () => {
  assert.equal(cleanupEditorPlaceholderLines('A\n\n\u00A0\n\nB'), 'A\n\n\nB')
})
