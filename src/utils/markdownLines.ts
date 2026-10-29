/**
 * Markdown 行级扫描的共用地基（零依赖）：围栏 / `$$` 公式识别 + 行内代码分段。
 *
 * 从 markdownHtml.ts 抽出：所有「逐行改写 Markdown 但必须绕开代码」的规则
 * （序列化痕迹回收、分屏预览转义、一键美化）都要共用这一处围栏识别，
 * 禁止各写一套——判定口径漂移就会出现「这边动了代码那边没动」。
 */

export const FENCE_LINE = /^ {0,3}(`{3,}|~{3,})(.*)$/

export type LineKind = 'fence' | 'math' | 'prose'

/** 围栏和 `$$` 公式整段原样跳过，只改普通行。所有行级规则共用这一处。 */
export function mapMarkdownLines(text: string, fn: (line: string, kind: LineKind) => string): string {
  const lines = text.split('\n')
  let fence: { char: string; len: number } | null = null
  let math = false
  const out = lines.map((line) => {
    const mark = FENCE_LINE.exec(line)
    if (mark && !(mark[1][0] === '`' && mark[2].includes('`'))) {
      const token = mark[1]
      const bare = mark[2].trim() === ''
      if (!fence) {
        fence = { char: token[0], len: token.length }
      } else if (fence.char === token[0] && token.length >= fence.len && bare) {
        fence = null
      }
      return fn(line, 'fence')
    }
    if (fence) return fn(line, 'fence')
    if (line.trim() === '$$') {
      math = !math
      return fn(line, 'math')
    }
    if (math) return fn(line, 'math')
    return fn(line, 'prose')
  })
  return out.join('\n')
}

/** 行内代码用成对反引号包住，中间的 `\*`、`<tag>` 是代码，不能按正文改。 */
export function mapInlineProse(line: string, fn: (prose: string) => string): string {
  const parts = line.split(/(`+)/)
  let inCode = false
  return parts
    .map((part) => {
      if (/^`+$/.test(part)) {
        inCode = !inCode
        return part
      }
      return inCode ? part : fn(part)
    })
    .join('')
}

/**
 * 模型输出的转义噪声回收（速记 AI 深度整理）：模型常把普通文本里的 `_`、`~` 无差别转义
 * （`A-_~!p` 变 `A-\_\~!p`），并用 HTML 实体保行尾空格（`&#x20;`）——渲染出来看着一样，
 * 源码已被污染。这里把「显示效果与没写一样」的噪声收回来：
 *
 * - `\_`/`\~` 全量还原：词中 `_` 在 CommonMark 里本来就不构成强调、单个 `~` 不成删除线，
 *   还原后与用户原文一致（成对才成的语法还原后也不会凭空配对，除非原文本来就配对）；
 * - `*` 只回收独立边界上的（成对 `\*..\*` 还原会变斜体，与 save 路径 restoreCrepeMarkdown
 *   的 `unescapeCrepeProse` 同口径，此处正则与它保持一致）；
 * - `&#x20;` 还原为普通空格（模型保行尾空格的实体写法）。
 *
 * 围栏、`$$` 公式、行内代码原样跳过——共用本模块的行分类与行内掩码，禁止另写一套。
 */
export function cleanModelMarkdownNoise(text: string): string {
  if (!text) return text
  return mapMarkdownLines(text, (line, kind) => {
    if (kind !== 'prose') return line
    return mapInlineProse(line, (prose) =>
      prose
        .replace(/\\([_~])/g, '$1')
        .replace(/&#x20;/gi, ' ')
        .replace(/(^|\s)\\\*(?=\s|$)/g, '$1*'),
    )
  })
}

// ─── 空行数量保真（源码 ⇄ 预览所见即所得）───────────────────────────────────
//
// Markdown 规范会把连续空行折叠成一次段落分隔：源码里敲 3 个空行，Crepe/marked
// 渲染出来只有 1 个段落间距，「所见非所得」。约定如下（两端共用，保证保存往返不漂移）：
//
//   源码里 m 个连续空行（m≥2）  ⇔  段落分隔 + (m−1) 个空段落
//   编辑器侧空段落填零宽 \u200B（与编辑器 placeholder 逻辑同款，斜杠菜单可触发）；
//   HTML 渲染侧空段落填 NBSP（\u00A0，marked 渲染成可见的空行）。
//
// 展开（装载侧）与回收（保存侧）互为逆操作：
//   expandBlankLines('A\n\n\nB')            === 'A\n\n\u200B\n\nB'
//   cleanupEditorPlaceholderLines(上者)      === 'A\n\n\nB'

/**
 * 装载侧：把 ≥2 连续空行的段插入 (m−1) 个 `fill` 空段落行。
 * 每个空段落行都必须被空行包围（`fill\n\n`），否则单换行会被解析成
 * 软换行（breaks: true 下是 <br>），空行就并进上一段了。
 * 围栏与 `$$` 公式里的空行是代码/公式正文，原样跳过。
 */
export function expandBlankLines(text: string, fill = '\u200B'): string {
  if (!text) return text
  // 快速路径：没有出现 3+ 连续换行（含行间空白）就没有待展开的空行段
  if (!/\n[ \t]*\n[ \t]*\n/.test(text)) return text
  // 文末换行是终止符不是空行：先剥掉再统计，处理完补回，否则每轮往返多出 1 个空行
  const hadEol = text.endsWith('\n')
  const rows: Array<{ line: string; kind: LineKind }> = []
  mapMarkdownLines(hadEol ? text.slice(0, -1) : text, (line, kind) => {
    rows.push({ line, kind })
    return line
  })
  const out: string[] = []
  let blanks = 0
  const flush = () => {
    if (!blanks) return
    out.push('')
    for (let i = 1; i < blanks; i++) out.push(fill, '')
    blanks = 0
  }
  for (const { line, kind } of rows) {
    if (kind === 'prose' && line.trim() === '') {
      blanks++
      continue
    }
    flush()
    out.push(line)
  }
  flush()
  const result = out.join('\n')
  return hadEol ? `${result}\n` : result
}

/**
 * 保存侧：回收空段落占位行，还原成对应数量的空行。
 * ①占位行后紧跟空行 → 连同自身换行并入该空行：序列化「段\n\n\u200b\n\n段」
 *   回收为「段\n\n\n段」，空行数恰好 = 空段落数（与 expandBlankLines 互逆）；
 * ②其余位置（文末等）→ 清成真空行（维持旧版行为）。
 */
export function cleanupEditorPlaceholderLines(md: string): string {
  return md
    .replace(/^[\u200B\u200C\u200D\uFEFF\u00A0\t ]+\n(?=\n)/gm, '')
    .replace(/^[\u200B\u200C\u200D\uFEFF\u00A0\t ]+$/gm, '')
    // 文末残留的零宽/不可见占位（非整行）
    .replace(/[\u200B\u200C\u200D\uFEFF\u00A0]+$/g, '')
}

/** 列表末尾连按回车产生的空列表项：序列化成「1\.」（转义点号）或「-」之类的
 *  纯标记行，预览里渲染成只有序号/圆点的空项，源码里是乱码感的伪行 → 整行清掉。
 *  只作用于普通行，围栏/公式里的 `1\.`、`-` 是代码正文，不删。 */
const EMPTY_LIST_MARKER = /^\s*(?:\d{1,9}\\?\.\s*|\d{1,9}[）)]\s*|[-*+]\s+|>\s*)$/

export function dropEmptyListMarkerLines(md: string): string {
  return mapMarkdownLines(md, (line, kind) =>
    kind === 'prose' && EMPTY_LIST_MARKER.test(line) ? '' : line,
  )
}
