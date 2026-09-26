<script setup lang="ts">
/** Markdown 源码编辑器（CodeMirror 6 封装）。
 *  设计约束：
 *  - 主题完全走应用设计令牌（CSS 变量），亮/暗/preset 切换自动生效，无需 JS 重建主题；
 *    仅 darkTheme 布尔（影响 CM 默认选区/光标）经 Compartment 动态重配。
 *  - 查找替换统一走父级 FindReplaceBar，这里阻断 CM 内置搜索面板（Mod-f/Esc 语义让位），
 *    暴露 search API 供父级调用。
 *  - 输入法（composition）期间照常 emit——与旧 textarea 的 input 事件语义一致，
 *    保存链路本身防抖，且父级 setValue 前比对内容天然防循环。 */
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { Compartment, EditorState } from '@codemirror/state'
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, placeholder as cmPlaceholder } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { markdown, markdownLanguage, markdownKeymap } from '@codemirror/lang-markdown'
import { languages } from '@codemirror/language-data'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags as t } from '@lezer/highlight'
import {
  search,
  highlightSelectionMatches,
  SearchQuery,
  findNext,
  findPrevious,
  replaceNext,
  replaceAll,
  setSearchQuery,
  closeSearchPanel,
} from '@codemirror/search'

/** 行尾回车结构补全钩子（代码块/公式/图片/表格），返回 null 则走默认换行（含列表延续） */
type EnterTransform = (text: string, pos: number) => { value: string; cursor: number } | null

const props = defineProps<{
  modelValue: string
  placeholder?: string
  transformOnEnter?: EnterTransform
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'open-find', replace: boolean): void
  (e: 'close-find'): void
}>()

const hostEl = ref<HTMLDivElement | null>(null)
// EditorView 实例极复杂，必须 shallowRef：深响应式 Proxy 会破坏内部状态且类型不兼容
const viewRef = shallowRef<EditorView | null>(null)

/* ---- 亮/暗检测：观察根元素 data-theme，darkTheme 布尔经 Compartment 重配 ---- */
const themeComp = new Compartment()
function isDark(): boolean {
  return document.documentElement.getAttribute('data-theme') === 'dark'
}
let themeObserver: MutationObserver | null = null

// ---- 语法高亮：全部取应用令牌色，自动跟随亮暗与 preset。
// lezer-markdown 的标记符号（井号、星号、引用符等）统一映射为 processingInstruction，无独立 mark tag
const mdHighlight = HighlightStyle.define([
  { tag: t.heading1, fontSize: '1.45em', fontWeight: '700', color: 'var(--text-1)', margin: '0.35em 0' },
  { tag: t.heading2, fontSize: '1.3em', fontWeight: '700', color: 'var(--text-1)', margin: '0.3em 0' },
  { tag: t.heading3, fontSize: '1.18em', fontWeight: '700', color: 'var(--text-1)' },
  { tag: [t.heading4, t.heading5, t.heading6], fontWeight: '700', color: 'var(--text-1)' },
  { tag: t.heading, fontWeight: '700', color: 'var(--text-1)' },
  { tag: t.processingInstruction, color: 'var(--text-3)' },
  { tag: t.strong, fontWeight: '700', color: 'var(--text-1)' },
  { tag: t.emphasis, fontStyle: 'italic', color: 'var(--text-1)' },
  { tag: t.strikethrough, textDecoration: 'line-through', color: 'var(--text-3)' },
  { tag: t.link, color: 'var(--accent)', textDecoration: 'underline' },
  { tag: t.labelName, color: 'var(--c-blue-ink)' },
  { tag: t.url, color: 'var(--text-3)' },
  { tag: t.monospace, color: 'var(--c-red-ink)', backgroundColor: 'var(--brand-50)', borderRadius: '3px' },
  { tag: t.quote, color: 'var(--text-2)', fontStyle: 'normal' },
  { tag: t.contentSeparator, color: 'var(--text-3)' },
  { tag: t.escape, color: 'var(--c-orange)' },
  { tag: t.list, color: 'var(--text-1)' },
])

const baseEditorTheme = EditorView.theme({
  '&': {
    height: '100%',
    color: 'var(--text-1)',
    backgroundColor: 'transparent',
    fontSize: '13.5px',
  },
  '.cm-scroller': {
    fontFamily: "'Cascadia Code', 'JetBrains Mono', Consolas, 'Microsoft YaHei Mono', monospace",
    lineHeight: '1.7',
    padding: '12px 4px 40vh 12px',
  },
  '.cm-content': { caretColor: 'var(--accent)' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--accent)' },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection': { backgroundColor: 'var(--brand-50)' },
  '.cm-gutters': {
    backgroundColor: 'transparent',
    color: 'var(--text-4)',
    border: 'none',
    paddingLeft: '4px',
  },
  '.cm-activeLineGutter, .cm-activeLine': { backgroundColor: 'transparent' },
  '.cm-selectionMatch': { backgroundColor: 'var(--brand-50)', outline: '1px solid var(--brand-glow)' },
  '&.cm-focused': { outline: 'none' },
  '.cm-line': { padding: '0 10px' },
  '.cm-placeholder': { color: 'var(--text-3)' },
  '.cm-searchMatch': { backgroundColor: 'var(--c-yellow)', color: 'var(--text-1)', borderRadius: '2px' },
  '.cm-searchMatch-selected': { backgroundColor: 'var(--c-orange)', color: '#fff' },
})

/* ---- keymap：Mod-f/Mod-h 让位给统一查找替换浮条 ---- */
const overrideKeymap = keymap.of([
  { key: 'Mod-f', run: () => { emit('open-find', false); return true } },
  { key: 'Mod-h', run: () => { emit('open-find', true); return true } },
  { key: 'Escape', run: () => { emit('close-find'); return false } },
  // 行尾结构补全（优先于列表延续）：仅无选区时触发，行为与旧 textarea 版 onSourceKeydown 一致
  {
    key: 'Enter',
    run: () => {
      const view = viewRef.value
      const fn = props.transformOnEnter
      if (!view || !fn || view.state.selection.main.from !== view.state.selection.main.to) return false
      const res = fn(view.state.doc.toString(), view.state.selection.main.from)
      if (!res) return false
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: res.value },
        selection: { anchor: res.cursor },
        scrollIntoView: true,
      })
      return true
    },
  },
])

function createView(): EditorView {
  const state = EditorState.create({
    doc: props.modelValue,
    extensions: [
      lineNumbers(),
      highlightActiveLineGutter(),
      highlightActiveLine(),
      drawSelection(),
      history(),
      EditorView.lineWrapping,
      cmPlaceholder(props.placeholder ?? ''),
      markdown({ codeLanguages: languages, base: markdownLanguage }),
      syntaxHighlighting(mdHighlight),
      search({ top: false }),
      highlightSelectionMatches(),
      overrideKeymap,
      keymap.of([...markdownKeymap, ...defaultKeymap, ...historyKeymap, indentWithTab]),
      themeComp.of([baseEditorTheme, EditorView.darkTheme.of(isDark())]),
      EditorView.updateListener.of((u) => {
        if (u.docChanged) emit('update:modelValue', u.state.doc.toString())
      }),
    ],
  })
  return new EditorView({ state, parent: hostEl.value! })
}

onMounted(() => {
  viewRef.value = createView()
  // 根元素 data-theme 变化 → 仅重配 darkTheme 布尔（视觉层全靠 CSS 变量自动跟随）
  themeObserver = new MutationObserver(() => {
    viewRef.value?.dispatch({
      effects: themeComp.reconfigure([baseEditorTheme, EditorView.darkTheme.of(isDark())]),
    })
  })
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})

onBeforeUnmount(() => {
  themeObserver?.disconnect()
  themeObserver = null
  viewRef.value?.destroy()
  viewRef.value = null
})

/* ---- 外部内容同步：值一致时跳过，天然防 emit 循环 ---- */
watch(
  () => props.modelValue,
  (v) => {
    const view = viewRef.value
    if (!view) return
    if (view.state.doc.toString() === v) return
    const sel = view.state.selection.main
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: v },
      // 外部整体替换（切笔记）时光标位置通常失效，钳制到新文末尾附近
      selection: { anchor: Math.min(sel.anchor, v.length) },
    })
  },
)

/* ---- 供父级（FindReplaceBar / 大纲）调用 ---- */
function focusEditor(): void {
  viewRef.value?.focus()
}

function setValue(v: string): void {
  const view = viewRef.value
  if (!view || view.state.doc.toString() === v) return
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: v } })
}

/** 大纲跳转：选中该行并滚动到可视区 */
function scrollToLine(line: number): void {
  const view = viewRef.value
  if (!view) return
  const n = Math.max(1, Math.min(line, view.state.doc.lines))
  const l = view.state.doc.line(n)
  view.dispatch({ selection: { anchor: l.from }, effects: EditorView.scrollIntoView(l.from, { y: 'center' }) })
  view.focus()
}

/** 写入查找状态（供 FindReplaceBar 同步 query），后续 findNext/replaceNext 即用此 query */
function applySearchQuery(q: SearchQuery): void {
  viewRef.value?.dispatch({ effects: setSearchQuery.of(q) })
}

function findNextMatch(): boolean {
  return viewRef.value ? findNext(viewRef.value) : false
}
function findPrevMatch(): boolean {
  return viewRef.value ? findPrevious(viewRef.value) : false
}
function replaceNextMatch(): boolean {
  return viewRef.value ? replaceNext(viewRef.value) : false
}
function replaceAllMatches(): boolean {
  return viewRef.value ? replaceAll(viewRef.value) : false
}
function closeFind(): void {
  const view = viewRef.value
  if (!view) return
  closeSearchPanel(view) // 若内置面板意外打开过则关闭；未打开时无操作
}

function getText(): string {
  return viewRef.value?.state.doc.toString() ?? ''
}

function getSelection(): { from: number; to: number } {
  const s = viewRef.value?.state.selection.main
  return { from: s?.from ?? 0, to: s?.to ?? 0 }
}

/** 全文替换并同时设定选区（工具栏变换路径：一次 dispatch，避免 adoptMarkdown 回流二次覆盖） */
function setDocWithSelection(text: string, anchor: number, head: number): void {
  const view = viewRef.value
  if (!view) return
  view.dispatch({
    changes: { from: 0, to: view.state.doc.length, insert: text },
    selection: { anchor: Math.min(anchor, text.length), head: Math.min(head, text.length) },
    scrollIntoView: true,
  })
}

defineExpose({
  view: viewRef,
  getText,
  getSelection,
  setDocWithSelection,
  focusEditor,
  setValue,
  scrollToLine,
  applySearchQuery,
  findNextMatch,
  findPrevMatch,
  replaceNextMatch,
  replaceAllMatches,
  closeFind,
})
</script>

<template>
  <div ref="hostEl" class="cm-host"></div>
</template>

<style scoped>
.cm-host {
  height: 100%;
  overflow: hidden;
}
.cm-host :deep(.cm-editor) {
  height: 100%;
}
</style>
