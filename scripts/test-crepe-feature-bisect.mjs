// 用真实 Crepe 类 + feature 开关二分：找出让表格内容挂载失败的 feature
import { JSDOM } from 'jsdom'
const dom = new JSDOM('<!DOCTYPE html><html><body><div id="root"></div></body></html>', { pretendToBeVisual: true, url: 'http://localhost/' })
globalThis.window = dom.window
globalThis.document = dom.window.document
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true })
for (const k of ['Node','Element','HTMLElement','DocumentFragment','KeyboardEvent','MouseEvent','CustomEvent','Selection','Range','MutationObserver','ResizeObserver','IntersectionObserver','CSS','DOMParser','XMLSerializer','NodeFilter','Text','Comment','Event','InputEvent','UIEvent','PointerEvent','WheelEvent','DragEvent','SVGElement','SVGGraphicsElement','HTMLSpanElement','HTMLImageElement','HTMLInputElement','HTMLTextAreaElement','HTMLIFrameElement','HTMLCanvasElement','HTMLVideoElement','HTMLAudioElement','getComputedStyle','FileReader','File','Blob','FormData','CustomEvent']) {
  if (dom.window[k] !== undefined) { try { Object.defineProperty(globalThis, k, { value: dom.window[k], configurable: true }) } catch {} }
}
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window)
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window)
globalThis.dispatchEvent = dom.window.dispatchEvent.bind(dom.window)
globalThis.location = dom.window.location
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16)
globalThis.cancelAnimationFrame = clearTimeout

const TABLE = '| 列A | 列B |\n| --- | --- |\n| 甲 | 乙 |\n'
const { Crepe } = await import('@milkdown/crepe')
const { remarkLineBreak } = await import('@milkdown/kit/preset/commonmark')
const { forkHighlightRemark, highlightMark } = await import('../src/utils/forkHighlight.ts')

const FEATURES = Object.entries(Crepe.Feature).filter(([k]) => k !== 'AI')

async function trial(label, disable) {
  const root = document.getElementById('root')
  root.innerHTML = ''
  const features = {}
  for (const [, v] of FEATURES) features[v] = true
  for (const d of disable) features[d] = false
  features[Crepe.Feature.AI] = false
  const crepe = new Crepe({ root, defaultValue: TABLE, features })
  try {
    const t = setTimeout(() => { console.log(`[${label}] ❌ 超时`); process.exit(3) }, 6000)
    await crepe.create()
    clearTimeout(t)
    const tb = root.querySelectorAll('table').length
    console.log(`[${label}] ✓ (table DOM=${tb})`)
    await crepe.destroy()
    return true
  } catch (err) {
    console.log(`[${label}] ❌`, String(err).slice(0, 140))
    try { await crepe.destroy() } catch {}
    return false
  }
}

console.log('features:', FEATURES.map(([k, v]) => `${k}=${v}`).join(', '))
const root0 = document.getElementById('root')
{
  const c = new Crepe({ root: root0, defaultValue: TABLE, features: { [Crepe.Feature.AI]: false } })
  const variants = [
    ['仅remarkLineBreak', [remarkLineBreak]],
    ['仅forkHighlight+mark', [forkHighlightRemark, highlightMark]],
    ['全部', [remarkLineBreak, forkHighlightRemark, highlightMark]],
  ]
  for (const [label, exts] of variants) {
    const rr = document.createElement('div'); root0.appendChild(rr)
    const c2 = new Crepe({ root: rr, defaultValue: TABLE, features: { [Crepe.Feature.AI]: false } })
    for (const e2 of exts) c2.editor.use(e2)
    try { await c2.create(); console.log('[' + label + '] ✓ (table=' + rr.querySelectorAll('table').length + ')'); await c2.destroy() }
    catch (e) { console.log('[' + label + '] ❌', String(e).slice(0, 120)) }
  }
}
await trial('全开(无fork)', [])
await trial('关Latex', [Crepe.Feature.Latex])
await trial('关Latex+Table', [Crepe.Feature.Latex, Crepe.Feature.Table])
await trial('全关(仅builder)', FEATURES.map(([, v]) => v))
process.exit(0)
