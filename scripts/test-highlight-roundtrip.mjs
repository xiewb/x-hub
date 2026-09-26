// ==高亮== round-trip 冒烟验证：parse transformer 与 stringify handler 严格互逆
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkStringify from 'remark-stringify'
import remarkGfm from 'remark-gfm'

// 与 forkHighlight.ts 相同的 parse transformer
function highlightParse() {
  return (tree) => {
    const find = /==([^=\n]+)==/g
    const walk = (node) => {
      if (!node || !Array.isArray(node.children)) return
      let i = 0
      while (i < node.children.length) {
        const child = node.children[i]
        if (child.type === 'text' && typeof child.value === 'string') {
          find.lastIndex = 0
          if (find.test(child.value)) {
            find.lastIndex = 0
            const result = []
            let start = 0
            let m
            while ((m = find.exec(child.value))) {
              if (m.index > start) result.push({ type: 'text', value: child.value.slice(start, m.index) })
              result.push({ type: 'highlight', children: [{ type: 'text', value: m[1] }] })
              start = m.index + m[0].length
            }
            if (start < child.value.length) result.push({ type: 'text', value: child.value.slice(start) })
            node.children.splice(i, 1, ...result)
            i += result.length
            continue
          }
        }
        walk(child)
        i++
      }
    }
    walk(tree)
  }
}

// 与 forkHighlight.ts 相同的 stringify handler 注入
function highlightStringify() {
  const data = this.data()
  data.toMarkdownExtensions = data.toMarkdownExtensions || []
  data.toMarkdownExtensions.push({
    handlers: {
      highlight(node, _parent, state) {
        const exit = state.enter('highlight')
        const value = state.containerPhrasing(node, { before: '=', after: '=' })
        exit()
        return `==${value}==`
      },
    },
  })
}

const proc = unified().use(remarkParse).use(remarkGfm).use(highlightParse).use(highlightStringify).use(remarkStringify)

const cases = [
  'a ==b== c',
  '==整行高亮==',
  '普通文本 无高亮',
  'a ==b== c ==d== e',
  '- 列表内 ==高亮项== 继续',
  '**粗体内 ==高亮==**',
  '`==代码内不高亮==`',
  'a ==b== c\nd 单换行 ==e==',
  '==包含 *斜体* 的 高亮==',
]

let pass = 0
let fail = 0
for (const src of cases) {
  const out = String(await proc.process(src))
  const ok = out.trim() === src.trim()
  if (ok) pass++
  else fail++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${JSON.stringify(src)}  =>  ${JSON.stringify(out.trim())}`)
}
console.log(`\n${pass} pass, ${fail} fail`)
