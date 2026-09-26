<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch, type Component } from 'vue'
import { Crepe } from '@milkdown/crepe'
import '@milkdown/crepe/theme/common/style.css'
import '@milkdown/crepe/theme/frame.css'
import { editorViewCtx } from '@milkdown/kit/core'
import type { Ctx } from '@milkdown/kit/ctx'
import { imageBlockSchema } from '@milkdown/kit/component/image-block'
import { codeBlockSchema, remarkLineBreak } from '@milkdown/kit/preset/commonmark'
import { createTable } from '@milkdown/kit/preset/gfm'
import { Fragment, type Node as ProseNode, type Schema } from '@milkdown/kit/prose/model'
import type { EditorView } from '@milkdown/kit/prose/view'
import { NodeSelection, TextSelection, type EditorState } from '@milkdown/kit/prose/state'
import { callCommand } from '@milkdown/kit/utils'
import { undoCommand, redoCommand } from '@milkdown/kit/plugin/history'
import { undo as cmUndo, redo as cmRedo } from '@codemirror/commands'
import {
  Bold,
  Code,
  Heading1,
  Heading2,
  Heading3,
  Highlighter,
  Italic,
  Link2,
  List,
  ListOrdered,
  ListTree,
  ListTodo,
  Minus,
  Quote,
  Redo2,
  SquareCode,
  Strikethrough,
  Tag as TagIcon,
  Trash2,
  Undo2,
  X,
} from 'lucide-vue-next'
import { isTauri, tauriApi, type Note, type Tag } from '../api/tauri'
import { useStore } from '../stores/workbench'
import { attachBlockDrag } from '../utils/blockDrag'
import { expandOnEnter, matchWysiwygLine, type LineShortcut } from '../utils/markdownEnter'
import { forkHighlightRemark, highlightMark } from '../utils/forkHighlight'
import CodeMirrorSource from './CodeMirrorSource.vue'
import FindReplaceBar from './FindReplaceBar.vue'
import {
  collectMatches,
  currentMatchIndex,
  gotoMatch,
  replaceMatch,
  replaceAllInView,
  countStringMatches,
  countStringMatchesBefore,
  type FindQuery,
} from '../utils/proseFind'
import { SearchQuery } from '@codemirror/search'
import { loosenHtmlBreaks, renderNoteMarkdown, restoreCrepeMarkdown } from '../utils/markdownHtml'
import { deriveNoteTitle } from '../utils/markdown'
import { NOTE_EDITOR_MODES, normalizeNoteEditorMode, type NoteEditorMode } from '../utils/noteEditorMode'
import { getQuickEmojis } from '../utils/emoji'
import { saveNoteImageFile } from '../utils/noteImage'
import { parseTimestamp } from '../utils/time'
import EmojiPicker from './EmojiPicker.vue'

/**
 * 速记编辑器：实时预览（Crepe 所见即所得）/ 分屏预览 / 源码。Markdown 为真相源，600ms 防抖落盘。
 * 模式记在配置 note_editor_mode，按用户记住，不按笔记。
 * 行尾回车补结构（三种模式同一套判断）：``` / $$ 闭合，未写完的图片补成 ![]()，
 * |列x行| 或表头行生成表格。实时预览里回车同样把 #、>、-、1.、---、- [ ]、- [x] 收成标题、引用、列表、分隔线和任务。
 * 图片（粘贴/拖拽/点击上传）统一由 Crepe 的上传管线处理：plugin-upload 的 handlePaste/
 * handleDrop + ImageBlock 的 onUpload 配置 → saveNoteImageFile（notes/images + xhub-note 协议）。
 * 注意勿再自建 DOM paste 监听——plugin-upload 已处理粘贴，叠加监听会导致图片重复插入。
 * 块拖拽（六点把手）为指针实现（utils/blockDrag.ts），绕开 Tauri 原生拖放对 HTML5 DnD 的拦截。
 */

const props = defineProps<{
  note: Readonly<Note> | null
}>()

const emit = defineEmits<{
  (e: 'save', id: number, title: string, content: string): void
  (e: 'delete', id: number): void
}>()

const store = useStore()

const mode = ref<NoteEditorMode>(normalizeNoteEditorMode(store.state.config.note_editor_mode))

const rootEl = ref<HTMLDivElement>()
type CmSourceInst = InstanceType<typeof CodeMirrorSource>
const splitSourceEl = ref<CmSourceInst | null>(null)
/** 实时源码模式的 textarea（工具栏变换需要选区） */
const sourceEl = ref<CmSourceInst | null>(null)
const previewEl = ref<HTMLDivElement | null>(null)
let splitResize: ResizeObserver | null = null

let crepe: Crepe | null = null
/** 当前 Crepe 挂在哪一个容器上。容器被换掉（v-if 重建）时必须重挂，不能只看 crepe 是否非空。 */
let mountedOn: HTMLElement | null = null
let mounting = false
/** 挂载期间又切换了笔记：完成后需按最新笔记重挂一次（否则编辑器停留旧内容、防抖保存会跨笔记污染） */
let remountQueued = false
let detachBlockDrag: (() => void) | null = null

const localTitle = ref('')
const localContent = ref('')
const dirty = ref(false)
const previewHtml = computed(() => renderNoteMarkdown(localContent.value))

// ---- 生命周期 ----
onBeforeUnmount(() => {
  flushPendingSave()
  stopOutlineTimer()
  detachImageListeners()
  // 防御：卸载瞬间可能仍在拖拽/预览中
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeUp)
  resizeCtx = null
  window.removeEventListener('keydown', onPreviewKeydown)
  splitResize?.disconnect()
  splitResize = null
  void destroyEditor()
})

async function destroyEditor() {
  detachBlockDrag?.()
  detachBlockDrag = null
  // 切笔记时 rootEl 是同一个 DOM 元素（v-if 分支没变，Vue 复用），必须在这里解绑：
  // 否则每切一次就多挂一套 load/click/pointerdown/keydown，而旧的解绑函数已被覆盖、
  // 再也调不到，表现为「切 N 次笔记后一次回车跑 N 遍」。
  detachImageListeners()
  const c = crepe
  crepe = null
  mountedOn = null
  if (c) {
    try {
      await c.destroy()
    } catch (e) {
      console.warn('Crepe 销毁异常', e)
    }
  }
  if (rootEl.value) rootEl.value.innerHTML = ''
}

async function mountEditor(content: string) {
  if (!rootEl.value) return
  if (mounting) {
    // Crepe 异步初始化期间再次切换笔记时不能静默吞掉挂载请求——记下重挂，本次完成后按最新笔记重来
    queuedMarkdown = content
    remountQueued = true
    return
  }
  mounting = true
  const wantId = props.note?.id ?? null
  try {
    await destroyEditor()
    const c = new Crepe({
      root: rootEl.value,
      defaultValue: loosenHtmlBreaks(content),
      // AI 特性需外部模型服务，保持纯本地
      features: { [Crepe.Feature.AI]: false },
      featureConfigs: {
        [Crepe.Feature.ImageBlock]: {
          onUpload: saveNoteImageFile,
          inlineOnUpload: saveNoteImageFile,
          blockOnUpload: saveNoteImageFile,
          // Crepe 默认文案为英文，以下统一汉化
          inlineUploadButton: '上传',
          inlineUploadPlaceholderText: '或粘贴图片链接',
          blockUploadButton: '上传图片',
          blockUploadPlaceholderText: '或粘贴图片链接',
          blockConfirmButton: '确认',
          blockCaptionPlaceholderText: '填写图片说明',
        },
        [Crepe.Feature.BlockEdit]: {
          // 把手悬停偏移 16→4px：配合收窄后的编辑区左右内边距（72px），
          // 保证把手（66px 宽 + offset）完整落在边距内，不翻转盖字、不触发横向滚动
          blockHandle: {
            getOffset: () => 4,
          },
          // 斜杠菜单扩展：在「插入」右侧新增「表情」分组
          // 快捷表情（最近使用优先）点击即插入；「更多表情…」打开完整选择器（分类/搜索/最近使用）
          buildMenu: (builder) => {
            const group = builder.addGroup('emoji', '表情')
            getQuickEmojis().forEach((it) => {
              group.addItem(`emoji-${it.e}`, {
                label: it.n,
                icon: it.e,
                onRun: () => insertEmojiText(it.e),
              })
            })
            group.addItem('emoji-more', {
              label: '更多表情…',
              icon: emojiMoreIcon,
              onRun: () => {
                removeSlashQuery()
                emojiPickerVisible.value = true
              },
            })
          },
          textGroup: {
            label: '文本',
            text: { label: '正文' },
            h1: { label: '一级标题' },
            h2: { label: '二级标题' },
            h3: { label: '三级标题' },
            h4: { label: '四级标题' },
            h5: { label: '五级标题' },
            h6: { label: '六级标题' },
            quote: { label: '引用' },
            divider: { label: '分割线' },
          },
          listGroup: {
            label: '列表',
            bulletList: { label: '无序列表' },
            orderedList: { label: '有序列表' },
            taskList: { label: '任务列表' },
          },
          advancedGroup: {
            label: '插入',
            image: { label: '图片' },
            codeBlock: { label: '代码块' },
            table: { label: '表格' },
            math: { label: '公式' },
          },
        },
        [Crepe.Feature.Placeholder]: {
          text: '开始记录…',
        },
        [Crepe.Feature.LinkTooltip]: {
          inputPlaceholder: '粘贴链接…',
        },
        [Crepe.Feature.Toolbar]: {
          boldLabel: '加粗',
          italicLabel: '斜体',
          strikethroughLabel: '删除线',
          codeLabel: '行内代码',
          linkLabel: '链接',
          latexLabel: '公式',
        },
      },
    })
    // 单换行修复：让段落内 text 的 \n 解析为 hardbreak（视觉换行），
    // 序列化仍输出干净的单换行（stringify 不跑 transformer，round-trip 无损），
    // 与实时预览 marked {breaks:true} 的语义保持一致，消除源码↔预览来回切换产生的空行
    c.editor.use(remarkLineBreak)
    // ==高亮== 扩展（fork）：remark 双向 transformer + mark schema
    c.editor.use(forkHighlightRemark).use(highlightMark)
    await c.create()
    if (!rootEl.value || (props.note?.id ?? null) !== wantId) {
      // create 期间笔记已切换/组件已卸载：本次实例作废，队列重挂最新笔记（不挂监听、不接管拖拽）
      remountQueued = true
      try {
        await c.destroy()
      } catch {
        /* 丢弃的实例，销毁异常无需处理 */
      }
      return
    }
    // create 之后再挂监听，避免初始化本身触发一次 markdownUpdated 造成假保存
    c.on((listener) => {
      listener.markdownUpdated((_ctx, markdown) => {
        onEdited(markdown)
      })
    })
    crepe = c
    mountedOn = rootEl.value
    attachImageListeners()
    // 块拖拽（六点把手）指针实现：create 完成后从 ctx 取 EditorView 接管把手拖拽
    c.editor.action((ctx) => {
      const view = ctx.get(editorViewCtx)
      detachBlockDrag = attachBlockDrag(() => view)
    })
    // 已缓存的图片不会再次触发 load：挂载完成后先按 attrs 同步一次宽度
    syncImageWidths()
  } catch (e) {
    console.error('Crepe 初始化失败', e)
  } finally {
    mounting = false
    if (remountQueued && props.note && rootEl.value && mode.value === 'wysiwyg') {
      remountQueued = false
      const next = queuedMarkdown ?? content
      queuedMarkdown = null
      void mountEditor(next)
    } else {
      remountQueued = false
      queuedMarkdown = null
    }
  }
}

// ---- 笔记切换 / 防抖保存 ----
// 定时器与标签状态声明必须在 watch 之前：immediate 回调在 setup 阶段同步执行，后置声明会触发 TDZ
let saveTimer: ReturnType<typeof setTimeout> | null = null
let lastNoteId: number | null = null
/** 挂载进行中又收到新内容时，结束后按这份 Markdown 重挂，避免用过期的笔记正文 */
let queuedMarkdown: string | null = null
const noteTags = ref<Tag[]>([])
const tagInputVisible = ref(false)
const tagInput = ref('')

// 必须同时观察 rootEl：Crepe 容器在 setup 阶段还没渲染，只盯笔记 id 时首次挂载会落空（约定 38 时序陷阱①）。
// flush:'post' 等本次渲染把容器交出来；容器晚一拍出现时，rootEl 变化会再进一次回调。
watch(
  [() => props.note?.id, rootEl],
  async ([id, el], prev) => {
    const prevId = prev?.[0]
    // 回调触发时 props.note 已是新笔记，Crepe 里仍是上一篇。先取出上一篇正文再落盘，避免写到新笔记上。
    if (typeof prevId === 'number' && prevId !== id) {
      if (mode.value === 'wysiwyg') {
        const captured = captureCrepeMarkdown()
        const restored = captured == null ? null : restoreCrepeMarkdown(captured)
        if (restored != null && restored !== localContent.value) {
          localContent.value = restored
          deriveTitleFromContent(restored)
          dirty.value = true
        }
      }
      flushLeavingNote(prevId)
    }
    if (!props.note) {
      await destroyEditor()
      syncLocal()
      noteTags.value = []
      return
    }
    const noteChanged = prevId !== id
    if (noteChanged) syncLocal()
    if (mode.value === 'wysiwyg') {
      // 源码/分屏没有这块容器。el 为空就等下一次 rootEl 赋值，不能当成「笔记没了」去清正文。
      if (el && (noteChanged || !crepe || mountedOn !== el)) void mountEditor(localContent.value)
    } else if (noteChanged) {
      await destroyEditor()
    }
    if (!noteChanged || !props.note || props.note.id !== id) return
    if (isTauri()) {
      // await 期间用户可能已切到第三篇，回来要再校验一次 id，
      // 否则标签行会显示上一篇的标签（点「移除」还会改错关系）
      const tags = await tauriApi.getNoteTags(id)
      if (props.note?.id === id) noteTags.value = tags
    } else {
      noteTags.value = []
    }
  },
  { immediate: true, flush: 'post' },
)

watch(
  () => store.state.config.note_editor_mode,
  (value) => {
    const next = normalizeNoteEditorMode(value)
    if (value !== next) {
      void store.setNoteEditorMode(next)
      return
    }
    if (next !== mode.value) void applyMode(next, false)
  },
)

function syncLocal() {
  localTitle.value = props.note?.title ?? ''
  localContent.value = props.note?.content ?? ''
  dirty.value = false
}

/** 立即落盘防抖中未保存的编辑（若存在），并取消挂起的定时器 */
function flushPendingSave() {
  if (!saveTimer) return
  clearTimeout(saveTimer)
  saveTimer = null
  if (dirty.value && lastNoteId !== null) {
    dirty.value = false
    emit('save', lastNoteId, normalizeTitle(localTitle.value), localContent.value)
  }
}

/** 空标题落库时归一为默认值，与新建笔记的初始标题一致（列表展示不出现空行） */
function normalizeTitle(title: string): string {
  const t = title.trim()
  return t ? t : '无标题笔记'
}

function onEdited(markdown: string) {
  if (!props.note || mode.value !== 'wysiwyg') return
  // Crepe 序列化会加上 \[ \* 并把列表/分隔线改写成星号。收回来再存，切到分屏才和实时预览一致。
  adoptMarkdown(restoreCrepeMarkdown(markdown))
  // ratio 等图片属性可能经撤销/属性事务变化，同步一次宽度（幂等、无强制布局）
  syncImageWidths()
}

/** 把一份 Markdown 收进当前笔记。内容没变就不重新排保存。 */
function adoptMarkdown(markdown: string) {
  if (!props.note || markdown === localContent.value) return
  localContent.value = markdown
  deriveTitleFromContent(markdown)
  scheduleSave()
}

/** 标题还是默认值时，从正文首行自动派生；用户一旦改过标题即不再接管 */
function deriveTitleFromContent(markdown: string) {
  if (localTitle.value !== '' && localTitle.value !== '无标题笔记') return
  const derived = deriveNoteTitle(markdown)
  if (derived) localTitle.value = derived
}

function captureCrepeMarkdown(): string | null {
  const c = crepe
  if (!c) return null
  try {
    return c.getMarkdown()
  } catch (e) {
    console.warn('读取编辑器 Markdown 失败', e)
    return null
  }
}

/** 离开当前笔记时立刻落盘。id 用离开前的那篇，不能用已经换上来的 props.note。 */
function flushLeavingNote(id: number) {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (!dirty.value) return
  dirty.value = false
  emit('save', id, normalizeTitle(localTitle.value), localContent.value)
}

/** CM updateListener → 防抖保存链路（与旧 textarea input 事件语义一致） */
function onSourceInput(value: string) {
  adoptMarkdown(value)
  if (mode.value === 'split') void nextTick(syncPreviewScroll)
}





/** 分屏时右边预览按左边源码的滚动比例跟着走。两边高度不同，对齐的是滚动条位置而不是某一行。 */
function syncPreviewScroll() {
  const source = splitSourceEl.value?.view?.scrollDOM
  const preview = previewEl.value
  if (!source || !preview) return
  const sourceMax = source.scrollHeight - source.clientHeight
  const previewMax = preview.scrollHeight - preview.clientHeight
  preview.scrollTop = sourceMax <= 0 || previewMax <= 0 ? 0 : (source.scrollTop / sourceMax) * previewMax
}

watch([splitSourceEl, previewEl], () => {
  splitResize?.disconnect()
  splitResize = null
  const source = splitSourceEl.value?.view?.scrollDOM
  const preview = previewEl.value
  if (!source || !preview) return
  splitResize = new ResizeObserver(() => syncPreviewScroll())
  splitResize.observe(source)
  splitResize.observe(preview)
  source.addEventListener('scroll', syncPreviewScroll, { passive: true })
  syncPreviewScroll()
})

/**
 * 实时预览里 Milkdown 要在标记后面加空格才变成对应节点，单独回车只是换行。
 * 捕获阶段接住回车，把整行快捷标记换成代码块、公式块、图片块、表格、标题、引用、列表或分隔线。
 */
function onCrepeKeydown(e: KeyboardEvent) {
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing || !crepe) return
  const target = e.target
  if (target instanceof HTMLElement && target.closest('input, textarea, .milkdown-slash-menu')) return
  let handled = false
  crepe.editor.action((ctx) => {
    const view = ctx.get(editorViewCtx)
    const { state } = view
    const { $from, empty } = state.selection
    // 第三个 `-` 会被 Milkdown 的输入规则收成分隔线，并选中这条线。
    // 这时默认回车会在线的上方再插一段（线是父节点第一个子节点时），光标回到「开始记录…」，看起来像没转成。
    if (!empty) {
      const selected = state.selection
      if (!(selected instanceof NodeSelection) || selected.node.type.name !== 'hr') return
      const paragraph = state.schema.nodes.paragraph
      if (!paragraph) return
      const after = selected.to
      let tr = state.tr
      const next = state.doc.resolve(after).nodeAfter
      if (!next || !next.isTextblock) tr = tr.insert(after, paragraph.create())
      const sel = TextSelection.findFrom(tr.doc.resolve(Math.min(after + 1, tr.doc.content.size)), 1, true)
      if (!sel) return
      view.dispatch(tr.setSelection(sel).scrollIntoView())
      view.focus()
      handled = true
      return
    }
    const parent = $from.parent
    if (!parent.isTextblock || parent.type.spec.code) return
    // 光标不在行尾时回车只是拆行，不能把整行快捷标记换掉
    if ($from.parentOffset !== parent.content.size) return
    const shortcut = matchWysiwygLine(parent.textContent)
    if (!shortcut) return
    const start = $from.before()
    const end = $from.after()
    if (shortcut.type === 'code' || shortcut.type === 'math') {
      const codeBlock = codeBlockSchema.type(ctx)
      if (!$from.node(-1).canReplaceWith($from.index(-1), $from.indexAfter(-1), codeBlock)) return
      const tr = state.tr.delete($from.start(), $from.end()).setBlockType($from.start(), $from.start(), codeBlock, {
        language: shortcut.type === 'math' ? 'LaTeX' : shortcut.language,
      })
      view.dispatch(tr.scrollIntoView())
      view.focus()
      handled = true
      return
    }
    if (shortcut.type === 'heading') {
      const heading = state.schema.nodes.heading
      if (!heading) return
      if (!$from.node(-1).canReplaceWith($from.index(-1), $from.indexAfter(-1), heading)) return
      const from = $from.start()
      const to = Math.min(from + shortcut.prefix, $from.end())
      let tr = state.tr
      if (to > from) tr = tr.delete(from, to)
      const pos = tr.mapping.map(from)
      tr = tr.setBlockType(pos, pos, heading, { level: shortcut.level })
      view.dispatch(tr.scrollIntoView())
      view.focus()
      handled = true
      return
    }
    if (shortcut.type === 'task') {
      const itemDepth = listItemDepth($from)
      if (itemDepth > 0) {
        const item = $from.node(itemDepth)
        if (!item.type.spec.attrs || !('checked' in item.type.spec.attrs)) return
        const from = $from.start()
        const to = Math.min(from + shortcut.prefix, $from.end())
        let tr = state.tr
        if (to > from) tr = tr.delete(from, to)
        const pos = tr.mapping.map($from.before(itemDepth))
        tr = tr.setNodeMarkup(pos, undefined, { ...item.attrs, checked: shortcut.checked })
        view.dispatch(tr.scrollIntoView())
        view.focus()
        handled = true
        return
      }
    }
    if (shortcut.type === 'hr') {
      const hrType = state.schema.nodes.hr ?? state.schema.nodes.horizontal_rule
      const paragraph = state.schema.nodes.paragraph
      if (!hrType || !paragraph) return
      const hr = hrType.create()
      const blank = paragraph.create()
      const fragment = Fragment.from([hr, blank])
      if (!$from.node(-1).canReplace($from.index(-1), $from.indexAfter(-1), fragment)) return
      let tr = state.tr.replaceWith(start, end, fragment)
      const sel = TextSelection.findFrom(tr.doc.resolve(Math.min(start + hr.nodeSize + 1, tr.doc.content.size)), 1, true)
      if (sel) tr = tr.setSelection(sel)
      view.dispatch(tr.scrollIntoView())
      view.focus()
      handled = true
      return
    }
    let node: ProseNode | null = null
    try {
      node = shortcutNode(ctx, state.schema, shortcut)
    } catch (err) {
      console.warn('快捷结构生成失败', err)
      return
    }
    if (!node) return
    if (!$from.node(-1).canReplaceWith($from.index(-1), $from.indexAfter(-1), node.type)) return
    let tr = state.tr.replaceWith(start, end, node)
    const cursor = cursorInShortcut(tr.doc, start, node.nodeSize, shortcut.type)
    if (cursor != null) {
      const sel = TextSelection.findFrom(tr.doc.resolve(cursor), 1, true)
      if (sel) tr = tr.setSelection(sel)
    }
    view.dispatch(tr.scrollIntoView())
    view.focus()
    handled = true
  })
  if (!handled) return
  e.preventDefault()
  e.stopPropagation()
}

function shortcutNode(ctx: Ctx, schema: Schema, shortcut: LineShortcut): ProseNode | null {
  if (shortcut.type === 'image') {
    return imageBlockSchema.type(ctx).create({
      src: shortcut.src,
      caption: shortcut.caption,
      ratio: 1,
    })
  }
  if (shortcut.type === 'table-size') return createTable(ctx, shortcut.rows, shortcut.cols)
  if (shortcut.type === 'table-row') return tableFromCells(schema, shortcut.cells)
  if (shortcut.type === 'blockquote' || shortcut.type === 'bullet' || shortcut.type === 'ordered' || shortcut.type === 'task') {
    return wrappedBlock(schema, shortcut)
  }
  return null
}

function wrappedBlock(
  schema: Schema,
  shortcut: Extract<LineShortcut, { type: 'blockquote' | 'bullet' | 'ordered' | 'task' }>,
): ProseNode | null {
  const paragraph = schema.nodes.paragraph
  if (!paragraph) return null
  const inner = shortcut.text ? paragraph.create(null, schema.text(shortcut.text)) : paragraph.create()
  if (shortcut.type === 'blockquote') {
    const quote = schema.nodes.blockquote
    return quote ? quote.create(null, inner) : null
  }
  const itemType = schema.nodes.list_item
  if (!itemType) return null
  const attrs: Record<string, unknown> = {}
  if (shortcut.type === 'ordered') {
    attrs.listType = 'ordered'
    attrs.label = `${shortcut.order}.`
  }
  if (shortcut.type === 'task') {
    if (!itemType.spec.attrs || !('checked' in itemType.spec.attrs)) return null
    attrs.checked = shortcut.checked
    attrs.listType = 'bullet'
    attrs.label = '•'
  }
  const item = itemType.create(attrs, inner)
  if (shortcut.type === 'ordered') {
    const list = schema.nodes.ordered_list
    return list ? list.create({ order: shortcut.order }, item) : null
  }
  const list = schema.nodes.bullet_list
  return list ? list.create(null, item) : null
}

function listItemDepth($from: EditorState['selection']['$from']): number {
  for (let depth = $from.depth; depth > 0; depth--) {
    if ($from.node(depth).type.name === 'list_item') return depth
  }
  return -1
}

function tableFromCells(schema: Schema, cells: string[]): ProseNode | null {
  const table = schema.nodes.table
  const headerRow = schema.nodes.table_header_row
  const header = schema.nodes.table_header
  const row = schema.nodes.table_row
  const cell = schema.nodes.table_cell
  const paragraph = schema.nodes.paragraph
  if (!table || !headerRow || !header || !row || !cell || !paragraph) return null
  const headerCells = cells.map((text) =>
    header.create(null, text ? paragraph.create(null, schema.text(text)) : paragraph.create()),
  )
  const bodyCells = cells.map(() => cell.createAndFill())
  if (bodyCells.some((item) => !item)) return null
  return table.create(null, [
    headerRow.create(null, headerCells),
    row.create(null, bodyCells as ProseNode[]),
  ])
}

/** 表格表头行的光标落到第一个数据格，其余落到新节点内部。 */
function cursorInShortcut(doc: ProseNode, start: number, size: number, type: LineShortcut['type']): number | null {
  if (type !== 'table-row') return Math.min(start + 1, doc.content.size)
  let cellPos: number | null = null
  doc.nodesBetween(start, Math.min(start + size, doc.content.size), (node, pos) => {
    if (cellPos != null) return false
    if (node.type.name === 'table_cell') {
      cellPos = pos + 1
      return false
    }
  })
  return cellPos
}

async function applyMode(next: NoteEditorMode, persist: boolean) {
  if (next === mode.value) return
  if (mode.value === 'wysiwyg') {
    const captured = captureCrepeMarkdown()
    if (captured != null) adoptMarkdown(restoreCrepeMarkdown(captured))
  }
  mode.value = next
  if (persist) void store.setNoteEditorMode(next)
  if (next !== 'wysiwyg') await destroyEditor()
  // 切回实时预览时容器会重新出现，上面的 rootEl watch 负责挂载
}

function onPreviewClick(e: MouseEvent) {
  const target = e.target
  if (!(target instanceof HTMLImageElement) || !target.src) return
  previewSrc.value = target.currentSrc || target.src
}

/** 标题输入（v-model 之外）：用户修改标题必须同样进入防抖保存链路，
 *  否则只在改正文时才落库——改完标题不改正文，标题永远不会保存（切换/重启即丢失） */
function onTitleInput() {
  scheduleSave()
}

// ---- 图片尺寸接管（宽度语义）----
// Crepe 的 onImageLoad 会把图片高度锁定为像素（style.height），宽度 auto——窗口放大后
// 高度不变、宽度随之不变，表现为「图片不跟随窗口变宽」。这里在 CSS 层解锁高度
// （height: auto !important），让宽度成为唯一尺寸维度，并按 ProseMirror attrs 的 ratio
// 恢复用户调整过的尺寸：ratio=1（默认）→ 响应式 min(自然宽, 100%)；ratio<1 → 百分比定宽。
// ratio 沿用 Crepe 的序列化通道（markdown 图片 alt，如 ![0.75](url)），跨会话持久化。

const IMAGE_BLOCK_HANDLE_PX = 26 // 右下角把手命中区边长（与 CSS 视觉一致）

let detachImageListeners: () => void = () => {}

/** 监听图片 load（不冒泡，用捕获）与点击/拖拽把手，随编辑器挂载/销毁配对 */
function attachImageListeners() {
  const root = rootEl.value
  if (!root) return
  root.addEventListener('load', onEditorImgLoad, true)
  root.addEventListener('click', onEditorClick)
  root.addEventListener('pointerdown', onEditorPointerDown, true)
  root.addEventListener('keydown', onCrepeKeydown, true)
  detachImageListeners = () => {
    root.removeEventListener('load', onEditorImgLoad, true)
    root.removeEventListener('click', onEditorClick)
    root.removeEventListener('pointerdown', onEditorPointerDown, true)
    root.removeEventListener('keydown', onCrepeKeydown, true)
    detachImageListeners = () => {}
  }
}

function onEditorImgLoad(e: Event) {
  const t = e.target
  if (!(t instanceof HTMLImageElement) || t.dataset.type !== 'image-block') return
  syncImageWidths()
}

/** 把 doc 里每个 image-block 的 attrs.ratio 应用到对应 DOM 图片（幂等，无强制布局） */
function syncImageWidths() {
  const c = crepe
  if (!c) return
  c.editor.action((ctx) => {
    const view = ctx.get(editorViewCtx)
    view.state.doc.descendants((node, pos) => {
      if (node.type.name !== 'image-block') return
      const dom = view.nodeDOM(pos)
      const img =
        dom instanceof Element
          ? dom.querySelector<HTMLImageElement>('img[data-type="image-block"]')
          : null
      if (img) applyImageWidth(img, Number(node.attrs.ratio) || 1)
    })
  })
}

function applyImageWidth(img: HTMLImageElement, ratio: number) {
  if (!img.naturalWidth) return // 尚未加载完成，load 后会再来
  if (ratio >= 0.995) {
    if (img.style.width) img.style.removeProperty('width')
    return
  }
  const w = `${(ratio * 100).toFixed(2)}%`
  if (img.style.width !== w) img.style.width = w
}

function findImageBlockAt(view: EditorView, img: HTMLImageElement): { node: ProseNode; pos: number } | null {
  let found: { node: ProseNode; pos: number } | null = null
  view.state.doc.descendants((node, pos) => {
    if (found) return false
    if (node.type.name !== 'image-block') return
    const dom = view.nodeDOM(pos)
    if (dom instanceof Element && dom.contains(img)) {
      found = { node, pos }
      return false
    }
  })
  return found
}

// ---- 拖拽调整图片宽度 ----
interface ResizeCtx {
  img: HTMLImageElement
  startX: number
  startW: number
  base: number
}
let resizeCtx: ResizeCtx | null = null

function isHandleZone(wrapper: Element, e: { clientX: number; clientY: number }): boolean {
  const r = wrapper.getBoundingClientRect()
  return e.clientX >= r.right - IMAGE_BLOCK_HANDLE_PX && e.clientY >= r.bottom - IMAGE_BLOCK_HANDLE_PX
}

function onEditorPointerDown(e: PointerEvent) {
  if (e.button !== 0 || !crepe) return
  const target = e.target
  if (!(target instanceof Element)) return
  const wrapper = target.closest<HTMLElement>('.milkdown-image-block .image-wrapper')
  if (!wrapper || !isHandleZone(wrapper, e)) return
  const img = wrapper.querySelector<HTMLImageElement>('img[data-type="image-block"]')
  if (!img || !img.naturalWidth) return
  // 阻断 PM 的 mousedown 兼容链（取消 pointerdown 即抑制后续 mouse 事件），避免拖拽时选中节点
  e.preventDefault()
  e.stopPropagation()
  const block = img.closest('.milkdown-image-block')
  const startW = img.getBoundingClientRect().width
  const base = block
    ? Math.min(img.naturalWidth, block.getBoundingClientRect().width) || startW
    : startW
  resizeCtx = { img, startX: e.clientX, startW, base }
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', onResizeUp)
}

function onResizeMove(e: PointerEvent) {
  if (!resizeCtx) return
  // 鼠标移出窗口后松键不会派发 pointerup：buttons 归零即视为拖拽结束
  if (!e.buttons) {
    onResizeUp()
    return
  }
  e.preventDefault()
  const w = Math.max(60, resizeCtx.startW + (e.clientX - resizeCtx.startX))
  // px 定宽拖动；上限由 CSS max-width:100% 兜底（超宽自动停在容器宽）
  resizeCtx.img.style.width = `${Math.round(w)}px`
}

function onResizeUp() {
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeUp)
  const ctx = resizeCtx
  resizeCtx = null
  if (!ctx || !crepe) return
  const finalW = ctx.img.getBoundingClientRect().width
  if (!ctx.base || !finalW) return
  let ratio = finalW / ctx.base
  if (ratio >= 0.98) ratio = 1 // 拖回默认宽度即恢复响应式
  ratio = Math.max(0.05, Math.round(ratio * 100) / 100)
  crepe.editor.action((actx) => {
    const view = actx.get(editorViewCtx)
    const found = findImageBlockAt(view, ctx.img)
    if (!found) return
    view.dispatch(
      view.state.tr.setNodeMarkup(found.pos, undefined, { ...found.node.attrs, ratio }),
    )
    view.focus()
  })
}

// ---- 点击图片预览（lightbox）----
const previewSrc = ref('')

function onEditorClick(e: MouseEvent) {
  if (previewSrc.value) return
  const target = e.target
  if (!(target instanceof Element)) return
  const block = target.closest<HTMLElement>('.milkdown-image-block')
  if (block) {
    // caption 输入框、右上角操作按钮（说明开关）不触发预览
    if (target.closest('.caption-input, .operation')) return
    const wrapper = target.closest('.image-wrapper')
    if (!wrapper) return
    if (isHandleZone(wrapper, e)) return
    const img = wrapper.querySelector<HTMLImageElement>('img[data-type="image-block"]')
    if (!img) return // 空上传态（无图片本体）
    previewSrc.value = img.currentSrc || img.src
    return
  }
  const inlineImg = target.closest<HTMLImageElement>('img.image-inline')
  if (inlineImg) previewSrc.value = inlineImg.currentSrc || inlineImg.src
}

function onPreviewKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') previewSrc.value = ''
}

watch(previewSrc, (v) => {
  if (v) window.addEventListener('keydown', onPreviewKeydown)
  else window.removeEventListener('keydown', onPreviewKeydown)
})

function scheduleSave() {
  if (!props.note) return
  dirty.value = true
  if (saveTimer) clearTimeout(saveTimer)
  lastNoteId = props.note.id
  saveTimer = setTimeout(() => {
    saveTimer = null
    if (props.note) {
      emit('save', props.note.id, normalizeTitle(localTitle.value), localContent.value)
    }
  }, 600)
}

// 只有「同一篇笔记」的 updated_at 变化才是保存成功后的回写，才可以清 dirty。
// 切笔记时 id 也变了，绝不能在这里清：本 watch 默认 flush:'pre'，会先于下面那个
// flush:'post' 的切笔记 watch 执行，dirty 被清成 false 后 flushLeavingNote 会直接返回，
// 最后一整段 600ms 防抖窗口内的编辑就此静默丢失（切笔记丢字）。
watch(
  () => [props.note?.id, props.note?.updated_at] as const,
  ([id], [prevId]) => {
    if (id === prevId) dirty.value = false
  },
)

// ---- 格式工具栏：三模式通用的 Markdown 文本变换 ----
type MdAction =
  | 'bold'
  | 'italic'
  | 'strike'
  | 'code'
  | 'highlight'
  | 'link'
  | 'h1'
  | 'h2'
  | 'h3'
  | 'ul'
  | 'ol'
  | 'task'
  | 'quote'
  | 'codeblock'
  | 'hr'
  | 'undo'
  | 'redo'

const WRAP_ACTIONS: Partial<Record<MdAction, [string, string, string]>> = {
  highlight: ['==', '==', '高亮文本'],
  bold: ['**', '加粗文字', '**'],
  italic: ['*', '斜体文字', '*'],
  strike: ['~~', '删除文字', '~~'],
  code: ['`', '代码', '`'],
  link: ['[', '链接文字', '](https://)'],
}

const PREFIX_ACTIONS: Partial<Record<MdAction, string>> = {
  h1: '# ',
  h2: '## ',
  h3: '### ',
  ul: '- ',
  task: '- [ ] ',
  quote: '> ',
}

/** 对 Markdown 源文本做包裹/行前缀变换，返回新文本与建议选区 */
function transformMarkdown(
  src: string,
  selStart: number,
  selEnd: number,
  action: MdAction,
): { text: string; selStart: number; selEnd: number } {
  // 包裹类：选中则包裹，已包裹则取消，无选中插入占位
  const wrap = WRAP_ACTIONS[action]
  if (wrap) {
    const [open, placeholder, close] = wrap
    const hasSel = selEnd > selStart
    const selected = src.slice(selStart, selEnd)
    if (
      hasSel &&
      src.slice(Math.max(0, selStart - open.length), selStart) === open &&
      src.slice(selEnd, selEnd + close.length) === close
    ) {
      const text =
        src.slice(0, selStart - open.length) + selected + src.slice(selEnd + close.length)
      return { text, selStart: selStart - open.length, selEnd: selEnd - open.length }
    }
    const body = hasSel ? selected : placeholder
    const insert = open + body + close
    const text = src.slice(0, selStart) + insert + src.slice(selEnd)
    return { text, selStart: selStart + open.length, selEnd: selStart + open.length + body.length }
  }

  // 分割线：文档末尾追加水平线
  if (action === 'hr') {
    const base = src.length > 0 && !src.endsWith('\n') ? src + '\n' : src
    const text = base + '\n---\n'
    return { text, selStart: text.length, selEnd: text.length }
  }

  // 代码块：选中内容用围栏包住
  if (action === 'codeblock') {
    const body = src.slice(selStart, selEnd) || '代码块'
    const insert = '```\n' + body + '\n```'
    const text = src.slice(0, selStart) + insert + src.slice(selEnd)
    return { text, selStart: selStart + 4, selEnd: selStart + 4 + body.length }
  }

  // 行前缀类（标题/列表/引用）：作用于选区覆盖的所有行；再按一次取消
  if (action === 'ol') {
    const ls = src.lastIndexOf('\n', selStart - 1) + 1
    let le = src.indexOf('\n', selEnd)
    if (le === -1) le = src.length
    const lines = src.slice(ls, le).split('\n')
    let at = 0
    const numbered = lines.map((l) => {
      if (l.trim() === '' && lines.length > 1) return l
      at += 1
      return at + '. ' + l.replace(/^\s*(-|\*|\d+\.)\s+/, '')
    })
    const newBlock = numbered.join('\n')
    const text = src.slice(0, ls) + newBlock + src.slice(le)
    return { text, selStart: ls, selEnd: ls + newBlock.length }
  }
  const prefix = PREFIX_ACTIONS[action]
  if (prefix) {
    const ls = src.lastIndexOf('\n', selStart - 1) + 1
    let le = src.indexOf('\n', selEnd)
    if (le === -1) le = src.length
    const lines = src.slice(ls, le).split('\n')
    const allHave = lines.every((l) => l.startsWith(prefix) || l.trim() === '')
    const changed = lines.map((l) => {
      if (l.trim() === '' && lines.length > 1) return l
      if (allHave) return l.startsWith(prefix) ? l.slice(prefix.length) : l
      // 去掉已有的其他列表/引用标记，避免叠加
      return prefix + l.replace(/^\s*(-\s\[[ x]\]\s|[-*]\s|\d+\.\s|>\s)/, '')
    })
    const newBlock = changed.join('\n')
    const text = src.slice(0, ls) + newBlock + src.slice(le)
    return { text, selStart: ls, selEnd: ls + newBlock.length }
  }
  return { text: src, selStart, selEnd }
}

// ---- 查找替换（三模式路由：wysiwyg→ProseMirror 事务，source/split 左栏→CM search API）----
const findVisible = ref(false)
const findWithReplace = ref(false)
const findSearch = ref('')
const findReplace = ref('')
const findCase = ref(false)
const findRegexp = ref(false)
const findTotal = ref(0)
const findCurrent = ref(0)

function findQuery(): FindQuery {
  return { search: findSearch.value, caseSensitive: findCase.value, regexp: findRegexp.value }
}

function cmSearchQuery(): SearchQuery {
  const q = findQuery()
  return new SearchQuery({ search: q.search, replace: findReplace.value, caseSensitive: q.caseSensitive, regexp: q.regexp })
}

/** 源码/分屏左栏的 CM 实例（wysiwyg 下为 null） */
function activeCm(): CmSourceInst | null {
  return mode.value === 'split' ? splitSourceEl.value : sourceEl.value
}

/** Crepe 的 ProseMirror view（未挂载/已销毁时 null） */
function pmView(): EditorView | null {
  if (!crepe) return null
  let v: EditorView | null = null
  crepe.editor.action((ctx) => {
    v = ctx.get(editorViewCtx)
  })
  return v
}

/** 重算匹配计数（query 变化/跳转/替换后调用） */
function refreshFindCount() {
  if (!findVisible.value) return
  const q = findQuery()
  if (!q.search) {
    findTotal.value = 0
    findCurrent.value = 0
    return
  }
  if (mode.value === 'wysiwyg') {
    const view = pmView()
    if (!view) return
    const matches = collectMatches(view.state, q)
    findTotal.value = matches.length
    const idx = currentMatchIndex(matches, view.state)
    findCurrent.value = idx >= 0 ? idx + 1 : matches.length ? 1 : 0
  } else {
    const cm = activeCm()
    const view = cm?.view
    if (!view) return
    const text = view.state.doc.toString()
    findTotal.value = countStringMatches(text, q)
    const sel = view.state.selection.main
    findCurrent.value = sel.empty
      ? 0
      : Math.min(countStringMatchesBefore(text, q, sel.from) + 1, findTotal.value || 1)
  }
}

/** wysiwyg：从光标处向后定位下一个匹配（无则回绕），thenStart 时从头开始 */
function pmStep(dir: 1 | -1) {
  const view = pmView()
  if (!view) return
  const matches = collectMatches(view.state, findQuery())
  findTotal.value = matches.length
  if (!matches.length) {
    findCurrent.value = 0
    return
  }
  let idx: number
  if (dir === 1) {
    idx = matches.findIndex((m) => m.from >= view.state.selection.to)
    if (idx === -1) idx = 0
  } else {
    idx = -1
    for (let i = matches.length - 1; i >= 0; i--) {
      if (matches[i].to <= view.state.selection.from) {
        idx = i
        break
      }
    }
    if (idx === -1) idx = matches.length - 1
  }
  gotoMatch(view, matches[idx])
  findCurrent.value = idx + 1
}

function onFindSearch(v: string) {
  findSearch.value = v
  if (mode.value !== 'wysiwyg') activeCm()?.applySearchQuery(cmSearchQuery())
  if (mode.value === 'wysiwyg') {
    // 新 query：光标归到选区起点，避免 next 跳过当前位置
    const view = pmView()
    if (view) view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, view.state.selection.from)))
  }
  refreshFindCount()
}

function onFindReplace(v: string) {
  findReplace.value = v
  if (mode.value !== 'wysiwyg') activeCm()?.applySearchQuery(cmSearchQuery())
}

function onFindCase(v: boolean) {
  findCase.value = v
  if (mode.value !== 'wysiwyg') activeCm()?.applySearchQuery(cmSearchQuery())
  refreshFindCount()
}

function onFindRegexp(v: boolean) {
  findRegexp.value = v
  if (mode.value !== 'wysiwyg') activeCm()?.applySearchQuery(cmSearchQuery())
  refreshFindCount()
}

function onFindNext() {
  if (mode.value === 'wysiwyg') pmStep(1)
  else {
    activeCm()?.findNextMatch()
    refreshFindCount()
  }
}

function onFindPrev() {
  if (mode.value === 'wysiwyg') pmStep(-1)
  else {
    activeCm()?.findPrevMatch()
    refreshFindCount()
  }
}

function onFindReplaceOne() {
  const text = findReplace.value
  if (mode.value === 'wysiwyg') {
    const view = pmView()
    if (!view) return
    const matches = collectMatches(view.state, findQuery())
    findTotal.value = matches.length
    const idx = currentMatchIndex(matches, view.state)
    if (idx >= 0) {
      replaceMatch(view, matches[idx], text)
    } else {
      // 当前不在匹配上：先定位下一个，不自动替换（避免误替换）
      pmStep(1)
      return
    }
  } else {
    activeCm()?.replaceNextMatch()
  }
  adoptMarkdownFromSource()
  refreshFindCount()
}

function onFindReplaceAll() {
  const text = findReplace.value
  if (mode.value === 'wysiwyg') {
    const view = pmView()
    if (!view) return
    const matches = collectMatches(view.state, findQuery())
    replaceAllInView(view, matches, text)
  } else {
    activeCm()?.replaceAllMatches()
  }
  adoptMarkdownFromSource()
  refreshFindCount()
}

/** CM 路径替换后内容在 view 里，需同步回保存链路（wysiwyg 路径事务后同样走这里） */
function adoptMarkdownFromSource() {
  const text = mode.value === 'wysiwyg' ? captureCrepeMarkdown() : activeCm()?.getText()
  if (text != null) adoptMarkdown(text)
}

function onOpenFind(replace: boolean) {
  if (replace) findWithReplace.value = true
  findVisible.value = true
  void nextTick(refreshFindCount)
}

function onCloseFind() {
  findVisible.value = false
  activeCm()?.closeFind()
}

// ---- 大纲导航 ----
interface OutlineItem {
  level: number
  text: string
  pos?: number // wysiwyg: ProseMirror 位置
  line?: number // source/split: 行号（1 起）
}
const outlineVisible = ref(false)
const outlineItems = ref<OutlineItem[]>([])
let outlineTimer: ReturnType<typeof setInterval> | null = null

function buildWysiwygOutline(items: OutlineItem[]): void {
  const view = pmView()
  if (!view) return
  view.state.doc.descendants((node, pos) => {
    if (node.type.name === 'heading') {
      items.push({ level: Number(node.attrs.level) || 1, text: node.textContent, pos })
    }
    return
  })
}

function buildSourceOutline(items: OutlineItem[]): void {
  const lines = localContent.value.split('\n')
  let inFence = false
  lines.forEach((ln, i) => {
    if (/^\s*(```|~~~)/.test(ln)) {
      inFence = !inFence
      return
    }
    if (inFence) return
    const m = /^(#{1,6})\s+(.*)$/.exec(ln)
    if (m) items.push({ level: m[1].length, text: m[2].trim(), line: i + 1 })
  })
}

/** 重建大纲；内容无变化时不触发响应式更新 */
function rebuildOutline() {
  const items: OutlineItem[] = []
  if (mode.value === 'wysiwyg') buildWysiwygOutline(items)
  else buildSourceOutline(items)
  if (JSON.stringify(items) !== JSON.stringify(outlineItems.value)) outlineItems.value = items
}

function toggleOutline() {
  outlineVisible.value = !outlineVisible.value
  if (outlineVisible.value) {
    rebuildOutline()
    // 面板打开期间轻量轮询（600ms 字符串对比），捕捉编辑中标题变化
    if (!outlineTimer) outlineTimer = setInterval(() => {
      if (outlineVisible.value) rebuildOutline()
    }, 600)
  } else stopOutlineTimer()
}

function stopOutlineTimer() {
  if (outlineTimer) {
    clearInterval(outlineTimer)
    outlineTimer = null
  }
}

function onOutlineClick(item: OutlineItem) {
  if (mode.value === 'wysiwyg') {
    const view = pmView()
    if (!view || item.pos == null) return
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, item.pos)).scrollIntoView())
    view.focus()
  } else {
    const cm = activeCm()
    if (cm && item.line != null) cm.scrollToLine(item.line)
  }
}

/** 编辑器面板级 Ctrl+F / Ctrl+H（捕获阶段，覆盖 Crepe 内容区；CM 内部同键已让位） */
function onPanelKeydown(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return
  const k = e.key.toLowerCase()
  if (k === 'f') {
    e.preventDefault()
    e.stopPropagation()
    onOpenFind(false)
  } else if (k === 'h') {
    e.preventDefault()
    e.stopPropagation()
    onOpenFind(true)
  }
}

function applyMdAction(action: MdAction) {
  if (!props.note) return
  // 历史操作走命令通道（非文本变换）：wysiwyg 用 Crepe 内置 history，源码/分屏用 CM history
  if (action === 'undo' || action === 'redo') {
    if (mode.value === 'wysiwyg') {
      if (!crepe) return
      crepe.editor.action(callCommand(action === 'undo' ? undoCommand.key : redoCommand.key))
      return
    }
    const view = activeCm()?.view
    if (!view) return
    void (action === 'undo' ? cmUndo(view) : cmRedo(view))
    return
  }
  if (mode.value === 'wysiwyg') {
    // Crepe 拿不到等价的源码光标位置，退化在文末操作；capture → 变换 → 重挂
    const md = captureCrepeMarkdown()
    if (md == null) return
    const { text } = transformMarkdown(md, md.length, md.length, action)
    adoptMarkdown(text)
    void nextTick(() => {
      if (rootEl.value && mode.value === 'wysiwyg') void mountEditor(localContent.value)
    })
    return
  }
  const cm = mode.value === 'split' ? splitSourceEl.value : sourceEl.value
  if (!cm) return
  const sel = cm.getSelection()
  const { text, selStart, selEnd } = transformMarkdown(cm.getText(), sel.from, sel.to, action)
  // 一次 dispatch 完成全文替换+选区恢复，再走 adoptMarkdown（回流时值一致自动跳过）
  cm.setDocWithSelection(text, selStart, selEnd)
  adoptMarkdown(text)
  cm.focusEditor()
}

const TOOLBAR_BUTTONS: { action: MdAction; title: string; icon: Component }[] = [
  { action: 'bold', title: '加粗', icon: Bold },
  { action: 'italic', title: '斜体', icon: Italic },
  { action: 'strike', title: '删除线', icon: Strikethrough },
  { action: 'h1', title: '一级标题', icon: Heading1 },
  { action: 'h2', title: '二级标题', icon: Heading2 },
  { action: 'h3', title: '三级标题', icon: Heading3 },
  { action: 'ul', title: '无序列表', icon: List },
  { action: 'ol', title: '有序列表', icon: ListOrdered },
  { action: 'task', title: '任务列表', icon: ListTodo },
  { action: 'quote', title: '引用', icon: Quote },
  { action: 'code', title: '行内代码', icon: Code },
  { action: 'highlight', title: '高亮', icon: Highlighter },
  { action: 'codeblock', title: '代码块', icon: SquareCode },
  { action: 'link', title: '链接', icon: Link2 },
  { action: 'hr', title: '分割线', icon: Minus },
  { action: 'undo', title: '撤销 (Ctrl+Z)', icon: Undo2 },
  { action: 'redo', title: '重做 (Ctrl+Y)', icon: Redo2 },
]

// ---- 标签 ----
async function persistTags() {
  if (!props.note || !isTauri()) return
  await tauriApi.setNoteTags(props.note.id, noteTags.value.map((t) => t.id))
}

async function addTag(tag: Tag) {
  if (noteTags.value.some((t) => t.id === tag.id)) return
  noteTags.value.push(tag)
  await persistTags()
}

function removeTag(tagId: number) {
  noteTags.value = noteTags.value.filter((t) => t.id !== tagId)
  void persistTags()
}

// 标签被全局删除（列表筛选栏 ×）后，同步摘掉底栏残留的已删标签
watch(
  () => store.state.tags.map((t) => t.id).join(','),
  () => {
    if (noteTags.value.length === 0) return
    const alive = new Set(store.state.tags.map((t) => t.id))
    if (noteTags.value.some((t) => !alive.has(t.id))) {
      noteTags.value = noteTags.value.filter((t) => alive.has(t.id))
    }
  },
)

async function submitTagInput() {
  const name = tagInput.value.trim()
  if (!name) {
    tagInputVisible.value = false
    return
  }
  try {
    const t = await store.createTag(name)
    await addTag(t)
    tagInput.value = ''
  } catch (e) {
    console.error('创建标签失败', e)
  }
  tagInputVisible.value = false
}

function formatSavedTime(iso: string): string {
  const t = new Date(parseTimestamp(iso))
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${t.getFullYear()}年${t.getMonth() + 1}月${t.getDate()}日${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`
}

// ---- 表情插入 ----
const emojiPickerVisible = ref(false)

/** 斜杠菜单「更多表情…」的图标（Material mood 风格，fill 型，与 Crepe 自带图标一致） */
const emojiMoreIcon = `
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z"/>
  </svg>
`

/** 光标前同一文本块内斜杠指令「/query」的起点；光标不在指令后则返回 null。
 *  斜杠菜单的自定义项（表情）不会像内置项那样清掉指令文本（内置项走 clearTextInCurrentBlock），
 *  插入表情/打开表情选择器前需先定位并删除它 */
function slashQueryStart(state: EditorState, from: number): number | null {
  const $from = state.doc.resolve(from)
  if ($from.depth === 0 || !$from.parent.inlineContent) return null
  const blockStart = $from.start()
  // leafText 占位符保证内联叶子节点（硬换行等）也是 1 字符，字符串下标与文档位置 1:1 对应
  const textBefore = state.doc.textBetween(blockStart, from, '\n', '\uFFFC')
  const m = /(?:^|\s)(\/[^\s]*)$/.exec(textBefore)
  if (!m) return null
  // m[0] 含可选前导（行首零宽或一个空白），指令起点 = 匹配起点 + 前导长度，
  // 即 m.index + (m[0].length - m[1].length)。直接用 m.index + m[1].length
  // 会落在指令中间甚至指令之外，导致替换/删除后斜杠指令残留。
  return blockStart + m.index + (m[0].length - m[1].length)
}

/** 删除光标前的斜杠指令文本（「更多表情…」入口用：先清指令再开选择器，取消选择也不留残渣） */
function removeSlashQuery() {
  const c = crepe
  if (!c) return
  c.editor.action((ctx) => {
    const view = ctx.get(editorViewCtx)
    const { state } = view
    const start = slashQueryStart(state, state.selection.from)
    if (start == null) return
    view.dispatch(state.tr.delete(start, state.selection.to))
  })
}

/** 在光标处插入文本（表情即纯文本，走 ProseMirror 事务，一次撤销步骤）；
 *  光标停在斜杠指令后时连指令一起替换，斜杠不残留（与其他菜单项行为一致） */
function insertEmojiText(text: string) {
  const c = crepe
  if (!c) return
  c.editor.action((ctx) => {
    const view = ctx.get(editorViewCtx)
    const { state } = view
    const { from, to } = state.selection
    const start = slashQueryStart(state, from) ?? from
    const tr = state.tr.insertText(text, start, to)
    view.dispatch(tr)
    view.focus()
  })
}

function onPickEmoji(e: string) {
  insertEmojiText(e)
}

// ---- 点击编辑区任意位置聚焦（需求：点空白处把光标落到文末，点在内容上则原地定位） ----
/** 编辑区内的浮层/专属交互元素：块把手、斜杠菜单、工具栏、链接气泡、图片块、间隙光标。
 *  命中这些时让位给各自逻辑，不抢焦点。 */
const EDITOR_FLOAT_UI_SELECTOR =
  '.milkdown-block-handle, .milkdown-slash-menu, .milkdown-toolbar, .milkdown-link-edit, ' +
  '.milkdown-link-preview, .milkdown-image-block, .crepe-image-block, .ProseMirror-gapcursor'

function onEditorAreaMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  const root = rootEl.value
  if (!root) return
  const target = e.target
  if (!(target instanceof Element)) return
  const pm = root.querySelector('.ProseMirror')
  if (!pm) return
  // 点击落在可编辑内容（含其内边距）上：ProseMirror 原生把光标定位到最近可输入点，不干预
  if (pm.contains(target)) return
  if (target.closest(EDITOR_FLOAT_UI_SELECTOR)) return
  // .milkdown 自身且命中滚动条区域（右缘/下缘）：是在拖滚动条，不动焦点
  if (target.classList.contains('milkdown')) {
    const el = target as HTMLElement
    if (e.offsetX >= el.clientWidth || e.offsetY >= el.clientHeight) return
  }
  // 空白/非可编辑区：阻止默认失焦，把光标送到全文最后一个可输入点（文档末尾）
  e.preventDefault()
  crepe?.editor.action((ctx) => {
    const view = ctx.get(editorViewCtx)
    view.dispatch(view.state.tr.setSelection(TextSelection.atEnd(view.state.doc)).scrollIntoView())
    view.focus()
  })
}
</script>

<template>
  <div class="card editor-panel" @keydown.capture="onPanelKeydown">
    <!-- 空状态 -->
    <div v-if="!note" class="editor-empty">
      <p>选择或新建笔记</p>
    </div>

    <!-- 编辑器内容 -->
    <template v-else>
      <header class="ed-header">
        <input
          v-model="localTitle"
          class="ed-title-input"
          type="text"
          maxlength="80"
          placeholder="笔记标题"
          @input="onTitleInput"
          @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
        />
        <div class="mode-switch" role="radiogroup" aria-label="编辑模式">
          <button
            v-for="item in NOTE_EDITOR_MODES"
            :key="item.id"
            type="button"
            role="radio"
            :aria-checked="mode === item.id"
            :class="{ on: mode === item.id }"
            @click="applyMode(item.id, true)"
          >
            {{ item.label }}
          </button>
        </div>
        <button
          class="icon-btn del"
          title="删除笔记"
          aria-label="删除笔记"
          @click="emit('delete', note.id)"
        >
          <Trash2 :size="14" :stroke-width="1.8" />
        </button>
      </header>

      <!-- 格式工具栏：三模式通用（Markdown 文本变换） -->
      <div class="md-toolbar" role="toolbar" aria-label="格式工具栏">
        <button
          v-for="b in TOOLBAR_BUTTONS"
          :key="b.action"
          type="button"
          class="md-tool-btn"
          :title="b.title"
          :aria-label="b.title"
          @click="applyMdAction(b.action)"
        >
          <component :is="b.icon" :size="14" :stroke-width="2" />
        </button>
        <span class="md-tool-sep" aria-hidden="true"></span>
        <button
          type="button"
          class="md-tool-btn"
          :class="{ active: outlineVisible }"
          title="大纲"
          aria-label="大纲"
          @click="toggleOutline"
        >
          <ListTree :size="14" :stroke-width="2" />
        </button>
      </div>

      <div class="ed-body">
      <div v-if="mode === 'wysiwyg'" ref="rootEl" class="crepe-root" @mousedown.capture="onEditorAreaMouseDown"></div>
      <CodeMirrorSource
        v-else-if="mode === 'source'"
        ref="sourceEl"
        class="md-source"
        :model-value="localContent"
        placeholder="开始记录…"
        :transform-on-enter="expandOnEnter"
        @update:model-value="onSourceInput"
        @open-find="onOpenFind"
        @close-find="onCloseFind"
      />
      <div v-else class="ed-split">
        <CodeMirrorSource
          ref="splitSourceEl"
          class="md-source"
          :model-value="localContent"
          placeholder="开始记录…"
          :transform-on-enter="expandOnEnter"
          @update:model-value="onSourceInput"
          @open-find="onOpenFind"
          @close-find="onCloseFind"
        />
        <div
          v-if="localContent.trim()"
          ref="previewEl"
          class="md-preview"
          aria-label="预览"
          v-html="previewHtml"
          @click="onPreviewClick"
        />
        <p v-else class="md-preview md-preview-empty">开始记录…</p>
      </div>

      <FindReplaceBar
        :visible="findVisible"
        :with-replace="findWithReplace"
        :total="findTotal"
        :current="findCurrent"
        @update:search="onFindSearch"
        @update:replace="onFindReplace"
        @update:case="onFindCase"
        @update:regexp="onFindRegexp"
        @next="onFindNext"
        @prev="onFindPrev"
        @replace-one="onFindReplaceOne"
        @replace-all="onFindReplaceAll"
        @close="onCloseFind"
      />

      <Transition name="outline-panel">
        <div v-if="outlineVisible" class="outline-panel">
          <div class="outline-head">
            <span>大纲</span>
            <button type="button" class="outline-close" title="关闭" @click="outlineVisible = false">
              <X :size="13" :stroke-width="2" />
            </button>
          </div>
          <div v-if="outlineItems.length" class="outline-list">
            <button
              v-for="(it, i) in outlineItems"
              :key="i"
              type="button"
              class="outline-item"
              :style="{ paddingLeft: (it.level - 1) * 12 + 8 + 'px' }"
              :title="it.text"
              @click="onOutlineClick(it)"
            >
              <span class="outline-lv">H{{ it.level }}</span>
              <span class="outline-text">{{ it.text || '（空标题）' }}</span>
            </button>
          </div>
          <p v-else class="outline-empty">暂无标题，用「# 标题」或斜杠菜单创建</p>
        </div>
      </Transition>
      </div>

      <!-- 底栏：左标签行 + 右保存状态 -->
      <footer class="ed-footer">
        <div class="tag-row">
          <TagIcon :size="13" :stroke-width="1.8" class="tag-row-icon" />
          <span
            v-for="t in noteTags"
            :key="t.id"
            class="tag-chip"
          >
            {{ t.name }}
            <button
              class="tag-chip-x"
              type="button"
              :title="`移除标签「${t.name}」`"
              :aria-label="`移除标签「${t.name}」`"
              @click="removeTag(t.id)"
            >
              ✕
            </button>
          </span>
          <template v-if="tagInputVisible">
            <input
              v-model="tagInput"
              class="tag-input"
              type="text"
              maxlength="20"
              placeholder="标签名，回车确认"
              @keydown.enter.prevent="submitTagInput"
              @keydown.esc="tagInputVisible = false"
            />
          </template>
          <button
            v-else
            class="tag-add"
            title="添加标签"
            aria-label="添加标签"
            @click="tagInputVisible = true"
          >
            +
          </button>
        </div>

        <span class="ed-wordcount" title="正文字符数">{{ localContent.length }} 字</span>
        <span class="ed-status" :class="{ dirty }">
          {{ dirty ? '编辑中…' : `已保存 ${formatSavedTime(note.updated_at)}` }}
        </span>
      </footer>

    </template>

    <EmojiPicker :visible="emojiPickerVisible" @select="onPickEmoji" @close="emojiPickerVisible = false" />

    <!-- 图片预览灯箱（瞬态表面，点击遮罩/关闭按钮/Esc 关闭） -->
    <Teleport to="body">
      <div
        v-if="previewSrc"
        class="img-lightbox"
        role="dialog"
        aria-modal="true"
        aria-label="图片预览"
        @click="previewSrc = ''"
      >
        <img :src="previewSrc" alt="图片预览" @click.stop />
        <button class="lb-close" type="button" aria-label="关闭预览" title="关闭 (Esc)" @click="previewSrc = ''">
          <X :size="16" :stroke-width="2" />
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.editor-panel {
  height: 100%;
  width: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 16px 10px;
  overflow: hidden;
  container-type: inline-size;
  /* 速记模块字号：全局基准 × 模块系数 */
  font-size: calc(1rem * var(--fs-notes, 1));
}

.editor-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-3);
  font-size: 0.875em;
}

.ed-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.ed-title-input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border-soft);
  background: var(--input-bg);
  border-radius: var(--radius-md);
  font-size: 1em;
  font-weight: 600;
  font-family: inherit;
  color: var(--text-1);
  outline: none;
  padding: 8px 14px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.ed-title-input:focus {
  border-color: var(--brand-500);
  box-shadow: var(--shadow-focus);
}

.ed-title-input::placeholder {
  color: var(--text-4);
  font-weight: 400;
}

.del:hover {
  color: var(--c-red);
  background: color-mix(in srgb, var(--c-red) 10%, transparent);
}

/* ==高亮== 扩展语法的视觉：富文本内 mark 元素（fork 自定义 schema 输出） */
.crepe-root mark.hl-mark,
.md-preview mark.hl-mark {
  padding: 0 3px;
  background: color-mix(in srgb, var(--c-yellow) 45%, transparent);
  color: inherit;
  border-radius: 3px;
}
[data-theme='dark'] .crepe-root mark.hl-mark,
[data-theme='dark'] .md-preview mark.hl-mark {
  background: color-mix(in srgb, var(--c-yellow) 32%, transparent);
}

/* 编辑主体包裹层：承载查找替换浮条定位，内部三模式互斥布局 */
.ed-body {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.crepe-root {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--border-soft);
  background: var(--input-bg);
  border-radius: var(--radius-md);
}

.crepe-root :deep(.milkdown) {
  height: 100%;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.mode-switch {
  display: flex;
  flex-shrink: 0;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--input-bg);
}

.mode-switch button {
  border: none;
  background: transparent;
  color: var(--text-3);
  font: inherit;
  font-size: 0.75em;
  line-height: 1.2;
  padding: 6px 8px;
  cursor: pointer;
}

.mode-switch button.on {
  background: var(--brand-50);
  color: var(--brand-500);
}

.mode-switch button:hover {
  color: var(--text-1);
}

.md-source {
  flex: 1;
  min-height: 0;
  width: 100%;
  resize: none;
  border: 1px solid var(--border-soft);
  background: var(--input-bg);
  border-radius: var(--radius-md);
  color: var(--text-1);
  font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 0.875em;
  line-height: 1.6;
  padding: 12px 14px;
  outline: none;
}

.md-source:focus {
  border-color: var(--brand-500);
  box-shadow: var(--shadow-focus);
}

.ed-split {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
}

.md-preview {
  min-width: 0;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overflow-wrap: anywhere;
  border: 1px solid var(--border-soft);
  background: var(--input-bg);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  color: var(--text-1);
  line-height: 1.6;
}

.md-preview-empty {
  margin: 0;
  color: var(--text-4);
}

.md-preview :deep(p),
.md-preview :deep(ul),
.md-preview :deep(ol),
.md-preview :deep(pre),
.md-preview :deep(blockquote) {
  margin: 0 0 0.6em;
}

.md-preview :deep(input[type='checkbox']) {
  margin: 0 6px 0 0;
  accent-color: var(--brand-500);
  vertical-align: -2px;
}

.md-preview :deep(h1),
.md-preview :deep(h2),
.md-preview :deep(h3),
.md-preview :deep(h4),
.md-preview :deep(h5),
.md-preview :deep(h6) {
  margin: 0.2em 0 0.4em;
  font-weight: 650;
  line-height: 1.3;
}

.md-preview :deep(img) {
  max-width: 100%;
  height: auto;
}

.md-preview :deep(.md-code) {
  margin: 0 0 0.6em;
  border: 1px solid var(--code-border);
  border-radius: 8px;
  background: var(--bg-code);
  overflow: hidden;
}

.md-preview :deep(.md-code-lang) {
  padding: 6px 12px;
  background: var(--bg-code-head);
  border-bottom: 1px solid var(--code-border);
  color: var(--code-text-dim);
  font-size: 0.6875em;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: lowercase;
}

.md-preview :deep(.md-code pre) {
  margin: 0;
  max-width: 100%;
  padding: 12px 14px;
  overflow: hidden;
  background: transparent;
  color: var(--code-text);
  font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 0.8125em;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.md-preview :deep(.md-code code) {
  font-family: inherit;
  color: inherit;
  background: transparent;
  white-space: inherit;
  overflow-wrap: inherit;
}

.md-preview :deep(table) {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
}

.md-preview :deep(th),
.md-preview :deep(td) {
  overflow-wrap: anywhere;
}

.md-preview :deep(a) {
  color: var(--brand-500);
}

.md-preview :deep(blockquote) {
  padding-left: 12px;
  border-left: 2px solid var(--border-strong);
  color: var(--text-2);
}

@container (max-width: 640px) {
  .ed-split {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  }
}

.ed-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 6px;
  border-top: 1px solid var(--border-soft);
}

/* 标签行 */
.tag-row {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-row-icon {
  color: var(--text-4);
  flex-shrink: 0;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 0.6875em;
  font-weight: 500;
  color: var(--brand-500);
  background: var(--brand-50);
  border-radius: var(--radius-pill);
  padding: 3px 6px 3px 9px;
}

.tag-chip-x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  font-size: calc(0.625rem * var(--fs-notes, 1));
  line-height: 1;
  padding: 0;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.tag-chip-x:hover {
  background: color-mix(in srgb, var(--c-red) 14%, transparent);
  color: var(--c-red);
}

.tag-add {
  width: 26px;
  height: 26px;
  border: 1px dashed var(--text-4);
  background: transparent;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: 0.8125em;
  cursor: pointer;
  transition: border-color 0.12s, color 0.12s;
}

.tag-add:hover {
  border-color: var(--brand-500);
  color: var(--brand-500);
}

.tag-input {
  width: 130px;
  border: 1px solid var(--border-soft);
  background: var(--input-bg);
  border-radius: var(--radius-sm);
  color: var(--text-1);
  font-size: 0.75em;
  font-family: inherit;
  padding: 4px 10px;
  outline: none;
}

.tag-input:focus {
  border-color: var(--brand-500);
}

.ed-status {
  flex-shrink: 0;
  font-size: 0.75em;
  color: var(--text-3);
}

.ed-status.dirty {
  color: var(--brand-500);
}

/* 图片预览灯箱（Teleport 到 body，瞬态表面允许 backdrop-filter） */
.img-lightbox {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--scrim);
  backdrop-filter: blur(10px);
  animation: lb-in 0.18s ease-out;
  cursor: zoom-out;
}

.img-lightbox img {
  max-width: 92vw;
  max-height: 90vh;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  cursor: default;
}

.lb-close {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-soft);
  border-radius: 50%;
  background: var(--bg-card);
  color: var(--text-2);
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: color 0.12s, border-color 0.12s, transform 0.12s;
}

.lb-close:hover {
  color: var(--text-1);
  border-color: var(--border-strong);
}

.lb-close:active {
  transform: scale(0.96);
}

@keyframes lb-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
</style>

<style>
/* Crepe 主题变量对齐应用设计令牌（全局块：高优先级选择器压过 frame.css 的 .milkdown 定义）。
   亮色基线 + [data-theme="dark"] 暗色覆盖，替代 Crepe 缺失的动态主题切换（Milkdown #1839） */
.crepe-root .milkdown {
  --crepe-base-font-size: calc(15px * var(--fs-notes, 1));
  --crepe-color-background: transparent;
  --crepe-color-on-background: var(--text-1);
  --crepe-color-surface: var(--input-bg);
  --crepe-color-surface-low: var(--input-bg);
  --crepe-color-on-surface: var(--text-2);
  --crepe-color-on-surface-variant: var(--text-3);
  /* outline 同时承担图标色（工具栏/块把手/链接气泡）与发丝线：必须用中性灰墨，
     不能映射 --border-soft（亮色为 55% 白，白图标叠白底工具栏不可见） */
  --crepe-color-outline: var(--text-3);
  --crepe-color-primary: var(--text-1);
  --crepe-color-inverse: var(--bg-card);
  --crepe-color-on-inverse: var(--text-2);
  --crepe-color-inline-code: var(--brand-500);
}

[data-theme='dark'] .crepe-root .milkdown {
  --crepe-color-secondary: #4d4d4d;
  --crepe-color-on-secondary: #d6d6d6;
  --crepe-color-hover: #232323;
  --crepe-color-selected: #2f2f2f;
  --crepe-color-inline-area: #2b2b2b;
}

/* 透底态（壁纸+透明，白墨形态）：工具栏/斜杠菜单/链接气泡/图片说明换深玻璃实底。
   浮层底原为 30% 烟玻璃（--input-bg），叠在亮部照片上时白图标（--text-1/--text-3 均翻白）会糊掉，
   这里收成近实底深玻璃 + 白系图标，与白墨态 toast/对话面板同一处理手法 */
html[data-wallpaper-clear='1'] .crepe-root .milkdown {
  --crepe-color-surface: rgba(28, 29, 41, 0.92);
  --crepe-color-surface-low: rgba(28, 29, 41, 0.92);
  --crepe-color-on-surface: rgba(255, 255, 255, 0.92);
  --crepe-color-on-surface-variant: rgba(255, 255, 255, 0.74);
  --crepe-color-outline: rgba(255, 255, 255, 0.62);
  --crepe-color-primary: #ffffff;
  --crepe-color-secondary: rgba(255, 255, 255, 0.14);
  --crepe-color-on-secondary: rgba(255, 255, 255, 0.92);
  --crepe-color-inverse: rgba(28, 29, 41, 0.95);
  --crepe-color-on-inverse: rgba(255, 255, 255, 0.92);
  --crepe-color-hover: rgba(255, 255, 255, 0.14);
  --crepe-color-selected: rgba(255, 255, 255, 0.22);
}

/* ---- 编辑器元素级排版精修（fork）：标题层级/代码块/表格/引用/hr，全走应用令牌 ---- */
.crepe-root .milkdown h1 {
  font-size: 1.6em;
  font-weight: 700;
  letter-spacing: 0.01em;
  margin: 0.9em 0 0.35em;
}
.crepe-root .milkdown h2 {
  font-size: 1.38em;
  font-weight: 700;
  margin: 0.85em 0 0.3em;
}
.crepe-root .milkdown h3 {
  font-size: 1.2em;
  font-weight: 700;
  margin: 0.8em 0 0.25em;
}
.crepe-root .milkdown h4,
.crepe-root .milkdown h5,
.crepe-root .milkdown h6 {
  font-size: 1.05em;
  font-weight: 700;
  margin: 0.75em 0 0.2em;
}
.crepe-root .milkdown p {
  margin: 0.35em 0;
  line-height: 1.75;
}
.crepe-root .milkdown .milkdown-code-block {
  border-radius: 10px;
  border: 1px solid var(--border-soft);
  overflow: hidden;
}
.crepe-root .milkdown .milkdown-code-block .cm-editor {
  background: var(--input-bg);
}
.crepe-root .milkdown .milkdown-table-block table,
.crepe-root .milkdown table {
  border-collapse: collapse;
}
.crepe-root .milkdown th {
  background: var(--bg-card-soft);
  font-weight: 600;
}
.crepe-root .milkdown th,
.crepe-root .milkdown td {
  border: 1px solid var(--border-strong);
  padding: 5px 10px;
}
.crepe-root .milkdown blockquote {
  border-left: 3px solid var(--brand-500);
  background: var(--brand-50);
  padding: 2px 12px;
  border-radius: 0 8px 8px 0;
  color: var(--text-2);
}
.crepe-root .milkdown hr {
  border: none;
  height: 1px;
  background: var(--border-strong);
  margin: 1em 0;
}
[data-theme='dark'] .crepe-root .milkdown blockquote {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}

/* 编辑区内边距：Crepe 默认 padding 60px 120px 过大（文字距卡片边缘 145px），收紧为上下 20 / 左右 72。
   左右 72px 是块把手悬停空间（把手 66px 宽 + offset 4px，见 featureConfigs 的 blockHandle.getOffset），
   再小会导致把手翻转盖住文字或触发横向滚动 */
.crepe-root .milkdown .ProseMirror {
  padding: 20px 72px;
  min-width: 0;
  overflow-wrap: anywhere;
}

/* 长行在栏宽内折行，不再把整块编辑区撑出横向滚动。
   代码块靠 white-space: break-spaces 让 CodeMirror 自己认出折行（光标、点击仍按视觉行计算）。 */
.crepe-root .milkdown .milkdown-code-block,
.crepe-root .milkdown .milkdown-table-block {
  max-width: 100%;
  min-width: 0;
}

.crepe-root .milkdown .cm-editor,
.crepe-root .milkdown .cm-scroller {
  max-width: 100%;
}

.crepe-root .milkdown .cm-scroller {
  overflow-x: hidden;
}

.crepe-root .milkdown .cm-content {
  flex-shrink: 1;
  max-width: 100%;
  white-space: break-spaces;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.crepe-root .milkdown .milkdown-table-block table {
  width: 100%;
  table-layout: fixed;
}

.crepe-root .milkdown .milkdown-table-block th,
.crepe-root .milkdown .milkdown-table-block td {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.crepe-root .milkdown .katex-display {
  max-width: 100%;
  overflow-x: auto;
}

/* 把手容器默认 margin 0 10px：随边距收窄一并去掉，保证把手完整落在边距内 */
.crepe-root .milkdown .milkdown-block-handle {
  margin: 0;
}

/* 斜杠菜单「表情」分组：emoji 字符作为图标（icon 字段），默认 16px 偏小，放大一档；
   svg 图标（更多表情…）尺寸由 CSS width/height 固定，不受 font-size 影响 */
.crepe-root .milkdown-slash-menu .menu-group .milkdown-icon {
  font-size: 20px;
  line-height: 1;
}

/* 引用块：Crepe 默认 padding-left 40px，文字离左侧引用条太远，收紧到贴条显示 */
.crepe-root .milkdown .ProseMirror blockquote {
  padding-left: 12px;
}

/* ---- 图片尺寸接管 ----
   Crepe onImageLoad 把图片高度锁成像素（style.height），窗口放大后图片不跟随变宽。
   这里解锁高度让宽度成为唯一尺寸维度：ratio=1（默认）→ max-width:100% 响应式占满内容区；
   ratio<1（用户拖拽调整过，见 NoteEditor 宽度把手）→ 按百分比定宽，同样随窗口缩放 */
.crepe-root .milkdown .milkdown-image-block img {
  height: auto !important;
}

/* Crepe 内置高度把手停用（row-resize 调高度的交互不可见也不直观，改为宽度把手） */
.crepe-root .milkdown .milkdown-image-block .image-resize-handle {
  display: none !important;
}

/* 自定义宽度把手：image-wrapper 右下角 22px 视觉区（命中判定 26px，见 IMAGE_BLOCK_HANDLE_PX），
   悬停浮现斜向三点，pointer 事件由 NoteEditor 在编辑器根上委托处理 */
.crepe-root .milkdown .milkdown-image-block .image-wrapper::after {
  content: '';
  position: absolute;
  right: 0;
  bottom: 0;
  width: 22px;
  height: 22px;
  border-radius: 0 0 6px 0;
  cursor: nwse-resize;
  opacity: 0;
  transition: opacity 0.15s;
  background:
    radial-gradient(2.5px circle at 5px 17px, var(--text-3) 98%, transparent),
    radial-gradient(2.5px circle at 11px 11px, var(--text-3) 98%, transparent),
    radial-gradient(2.5px circle at 17px 5px, var(--text-3) 98%, transparent);
  filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.35));
}

.crepe-root .milkdown .milkdown-image-block:hover .image-wrapper::after,
.crepe-root .milkdown .milkdown-image-block .image-wrapper:active::after {
  opacity: 0.9;
}

/* 格式工具栏：三模式通用，位于标题栏与正文之间 */
.md-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1px;
  padding: 0 6px 6px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-1);
}
.md-tool-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 24px;
  border-radius: var(--radius-sm);
  color: var(--text-3);
  transition: background 0.12s, color 0.12s;
}
.md-tool-btn:hover {
  background: var(--bg-card-soft);
  color: var(--text-1);
}
.md-tool-btn.active {
  background: var(--brand-50);
  color: var(--brand-500);
}
/* 工具栏功能分组分隔线（撤销重做与大纲之间的视觉断点） */
.md-tool-sep {
  width: 1px;
  height: 14px;
  margin: 0 4px;
  background: var(--border-strong);
  opacity: 0.5;
}

/* ---- 大纲导航面板（右上浮层，与查找替换条同风格） ---- */
.outline-panel {
  position: absolute;
  top: 8px;
  right: 16px;
  z-index: 55;
  display: flex;
  flex-direction: column;
  width: 248px;
  max-height: 62%;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg, 12px);
  background: var(--bg-card-solid);
  backdrop-filter: blur(18px) saturate(1.4);
  -webkit-backdrop-filter: blur(18px) saturate(1.4);
  box-shadow: 0 8px 28px rgba(30, 30, 60, 0.16);
  overflow: hidden;
}
.outline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 10px 5px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  border-bottom: 1px solid var(--border-soft);
}
.outline-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: var(--text-3);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
.outline-close:hover {
  background: var(--c-red);
  color: #fff;
}
.outline-list {
  overflow-y: auto;
  padding: 4px;
}
.outline-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 8px;
  font-size: 12px;
  color: var(--text-2);
  text-align: left;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
.outline-item:hover {
  background: var(--brand-50);
  color: var(--text-1);
}
.outline-lv {
  flex-shrink: 0;
  padding: 0 3px;
  font-size: 10px;
  line-height: 14px;
  color: var(--text-4);
  background: var(--bg-card-soft);
  border-radius: 3px;
}
.outline-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.outline-empty {
  padding: 14px 12px;
  font-size: 12px;
  color: var(--text-3);
}
.outline-panel-enter-active,
.outline-panel-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}
.outline-panel-enter-from,
.outline-panel-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
.md-tool-btn:active {
  background: var(--brand-50);
  color: var(--brand-500);
}
.ed-wordcount {
  margin-right: 10px;
  font-size: 0.6875em;
  color: var(--text-4);
}
</style>
