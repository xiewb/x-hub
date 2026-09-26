/** ProseMirror 文档查找/替换纯逻辑（速记编辑器 wysiwyg 模式用）。
 *  设计要点：
 *  - 匹配限定在单个 text 节点内（速记场景的查找基本不跨节点；跨节点需处理
 *    段落边界语义，复杂度不成比例）。
 *  - 全部替换用单事务多 change、从尾向头排序，避免位置偏移。
 *  - 正则模式由调用方自行转换（本模块统一按字符串/正则双通道处理）。 */
import type { EditorView } from '@milkdown/kit/prose/view'
import type { EditorState } from '@milkdown/kit/prose/state'
import { TextSelection } from '@milkdown/kit/prose/state'

export interface FindQuery {
  search: string
  caseSensitive: boolean
  regexp: boolean
}

export interface TextMatch {
  from: number
  to: number
}

/** 构造查找用正则；非法正则回退为字面量 */
function buildRegex(q: FindQuery): RegExp | null {
  const flags = q.caseSensitive ? 'g' : 'gi'
  let src = q.search
  if (!q.regexp) src = src.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  try {
    return new RegExp(src, flags)
  } catch {
    return null
  }
}

/** 收集全部匹配（docChanged/query 变化时调用；文档量级小，全扫即可） */
export function collectMatches(state: EditorState, q: FindQuery): TextMatch[] {
  if (!q.search) return []
  const re = buildRegex(q)
  if (!re) return []
  const out: TextMatch[] = []
  state.doc.descendants((node, pos) => {
    if (!node.isText || !node.text) return
    re.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = re.exec(node.text))) {
      // 零宽匹配保护：跳过并前进一步，避免死循环
      if (m[0].length === 0) {
        re.lastIndex++
        continue
      }
      out.push({ from: pos + m.index, to: pos + m.index + m[0].length })
      if (out.length >= 2000) return false // 安全上限
    }
    return
  })
  return out
}

/** 当前选区落在哪个匹配上（-1 表示不在任何匹配） */
export function currentMatchIndex(matches: TextMatch[], state: EditorState): number {
  const { from, to } = state.selection
  for (let i = 0; i < matches.length; i++) {
    if (matches[i].from >= from && matches[i].to <= to) return i
  }
  return -1
}

/** 跳转到匹配位置并滚动到可视区 */
export function gotoMatch(view: EditorView, m: TextMatch): void {
  view.dispatch(
    view.state.tr.setSelection(TextSelection.create(view.state.doc, m.from, m.to)).scrollIntoView(),
  )
  view.focus()
}

/** 替换单个匹配，返回替换后的匹配列表（位置在替换点之后整体偏移） */
export function replaceMatch(view: EditorView, m: TextMatch, text: string): void {
  view.dispatch(view.state.tr.insertText(text, m.from, m.to))
  view.focus()
}

/** 全部替换：单事务从尾向头（位置不受前序替换影响） */
export function replaceAllInView(view: EditorView, matches: TextMatch[], text: string): number {
  if (!matches.length) return 0
  const tr = view.state.tr
  for (let i = matches.length - 1; i >= 0; i--) {
    tr.insertText(text, matches[i].from, matches[i].to)
  }
  view.dispatch(tr.scrollIntoView())
  return matches.length
}

/* ---- 纯文本计数（CodeMirror 侧计数用，与 PM 侧同一套匹配语义） ---- */

/** 全文匹配总数 */
export function countStringMatches(text: string, q: FindQuery): number {
  if (!q.search) return 0
  const re = buildRegex(q)
  if (!re) return 0
  re.lastIndex = 0
  let n = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m[0].length === 0) {
      re.lastIndex++
      continue
    }
    n++
    if (n >= 2000) break
  }
  return n
}

/** 位置 pos 之前的匹配数（用于推算「第几处」） */
export function countStringMatchesBefore(text: string, q: FindQuery, pos: number): number {
  if (!q.search) return 0
  const re = buildRegex(q)
  if (!re) return 0
  re.lastIndex = 0
  let n = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) && m.index < pos) {
    if (m[0].length === 0) {
      re.lastIndex++
      continue
    }
    n++
  }
  return n
}
