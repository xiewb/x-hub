/** ==高亮== 扩展语法（fork 自定义，上游无此功能）。
 *  实现机制（与 preset-commonmark 的 remarkLineBreak 同类）：
 *  - parse：remark transformer 把 text 节点内的 ==x== 拆为 mdast 'highlight' 节点；
 *    行内代码/围栏代码内容是 code 节点而非 text，天然不会被误处理。
 *  - serialize：mark 的 toMarkdown runner 产出 mdast 'highlight' 节点，
 *    通过 unified 标准协议（file.data.toMarkdownExtensions）给 remark-stringify
 *    注入 handler，输出 ==内容==。stringify 的 handler 与 parse 的 transformer 严格互逆，
 *    round-trip 无损。
 *  - 工具栏走文本变换通道（插入 ==…== 源码文本），斜杠菜单走 toggleMark 命令。 */
import { $mark, $remark } from '@milkdown/kit/utils'

/** mdast 树遍历（等价 unist-util-visit 的 text 节点拆分语义，零依赖）：
 *  fn 返回数字表示该子节点位置被替换为多个节点，跳到新位置继续。 */
function walkText(
  node: { children?: any[] },
  fn: (n: any, index: number, parent: any) => number | void,
): void {
  if (!node || !Array.isArray(node.children)) return
  let i = 0
  while (i < node.children.length) {
    const child = node.children[i]
    const ret = fn(child, i, node)
    if (typeof ret === 'number') {
      i = ret
      continue
    }
    walkText(child, fn)
    i++
  }
}

export const forkHighlightRemark = $remark('forkHighlight', () => {
  function attacher(this: { data: (key: string, value?: unknown) => unknown }) {
    // serialize 侧：remark-stringify 的 handler 扩展（remark-gfm 同款注入协议）
    this.data('toMarkdownExtensions', {
      extensions: [
        {
          handlers: {
            highlight(node: any, _parent: unknown, state: any) {
              const exit = state.enter('highlight')
              const value = state.containerPhrasing(node, { before: '=', after: '=' })
              exit()
              return `==${value}==`
            },
          },
        },
      ],
    })
    // parse 侧：text 内 ==x== 拆为 highlight 节点
    return (tree: any) => {
      const find = /==([^=\n]+)==/g
      walkText(tree, (node, index, parent) => {
        if (!node.value || typeof node.value !== 'string' || node.type !== 'text') return
        find.lastIndex = 0
        if (!find.test(node.value)) return
        find.lastIndex = 0
        const result: any[] = []
        let start = 0
        let m: RegExpExecArray | null
        while ((m = find.exec(node.value))) {
          if (m.index > start) result.push({ type: 'text', value: node.value.slice(start, m.index) })
          result.push({ type: 'highlight', children: [{ type: 'text', value: m[1] }] })
          start = m.index + m[0].length
        }
        if (!parent || typeof index !== 'number' || result.length === 0) return
        if (start < node.value.length) result.push({ type: 'text', value: node.value.slice(start) })
        parent.children.splice(index, 1, ...result)
        return index + result.length
      })
    }
  }
  return attacher
})

/** mark 注册：$mark 单层 factory 即含 schema+plugin（$Mark.type(ctx) 取 prosemirror MarkType） */
export const highlightMark = $mark('highlight', () => ({
  parseDOM: [{ tag: 'mark' }],
  toDOM: () => ['mark', { class: 'hl-mark' }],
  parseMarkdown: {
    match: (node: any) => node.type === 'highlight',
    runner: (state: any, node: any, type: any) => {
      state.openNode(type)
      state.next(node.children)
      state.closeNode()
    },
  },
  toMarkdown: {
    match: (mark: any) => mark.type.name === 'highlight',
    runner: (state: any, mark: any) => {
      state.openNode('highlight')
      state.next(mark.children)
      state.closeNode()
    },
  },
}))
