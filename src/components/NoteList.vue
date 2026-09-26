<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ChevronLeft, Plus, RotateCcw, Search, StickyNote, Trash2, X } from 'lucide-vue-next'
import type { Note, Tag } from '../api/tauri'
import { isTauri, tauriApi } from '../api/tauri'
import { useStore } from '../stores/workbench'
import { markdownPlainText } from '../utils/markdown'
import { parseTimestamp } from '../utils/time'
import ConfirmDialog from './ConfirmDialog.vue'

const props = defineProps<{
  notes: readonly Note[]
  activeId: number | null
}>()

const emit = defineEmits<{
  (e: 'select', id: number): void
  (e: 'create'): void
  (e: 'delete', id: number): void
}>()

const store = useStore()

// ---- 标签筛选 ----
const activeTagId = ref<number | null>(null)
const tagMap = ref<Map<number, number[]>>(new Map()) // note_id -> tag_ids

async function refreshTagMap() {
  const rows = await store.loadNoteTagsMap()
  const map = new Map<number, number[]>()
  for (const row of rows) {
    const list = map.get(row.note_id) ?? []
    list.push(row.tag_id)
    map.set(row.note_id, list)
  }
  tagMap.value = map
}

onMounted(() => {
  void refreshTagMap()
})

// ---- 删除标签（仿待办模块：chip 上的 × → 确认 → 全局删除并摘除关联） ----
const removingTag = ref<Tag | null>(null)

async function removeTag(id: number) {
  try {
    await store.deleteTag(id)
    if (activeTagId.value === id) activeTagId.value = null
    await refreshTagMap()
  } catch (e) {
    console.error('删除标签失败', e)
  }
}

function confirmRemoveTag() {
  const tag = removingTag.value
  removingTag.value = null
  if (tag) void removeTag(tag.id)
}

// ---- 搜索：按标题或内容过滤（本地全量数据，量级小，直接 includes） ----
const searchText = ref('')

// ---- 排序：修改时间 / 创建时间 / 名称 / 大小，选择记在 localStorage ----
type SortKey = 'updated' | 'created' | 'name' | 'size'
const SORT_KEY_STORAGE = 'note_sort_key'
const sortKey = ref<SortKey>(
  (localStorage.getItem(SORT_KEY_STORAGE) as SortKey | null) ?? 'updated',
)
watch(sortKey, (v) => localStorage.setItem(SORT_KEY_STORAGE, v))

// ---- 过滤 + 排序 ----
const filteredNotes = computed(() => {
  let list = [...props.notes]
  const kw = searchText.value.trim().toLowerCase()
  if (kw) {
    list = list.filter(
      (n) => n.title.toLowerCase().includes(kw) || n.content.toLowerCase().includes(kw),
    )
  }
  if (activeTagId.value !== null) {
    list = list.filter((n) => tagMap.value.get(n.id)?.includes(activeTagId.value!))
  }
  switch (sortKey.value) {
    case 'created':
      list.sort((a, b) => parseTimestamp(b.created_at) - parseTimestamp(a.created_at))
      break
    case 'name':
      list.sort((a, b) => a.title.localeCompare(b.title, 'zh-CN'))
      break
    case 'size':
      list.sort((a, b) => b.content.length - a.content.length)
      break
    default:
      list.sort((a, b) => parseTimestamp(b.updated_at) - parseTimestamp(a.updated_at))
  }
  return list
})

// ---- 垃圾箱 ----
const trashMode = ref(false)
const trashNotes = ref<Note[]>([])
const purgingNote = ref<Note | null>(null)
const emptyTrashConfirm = ref(false)
const trashBusy = ref(false)

async function openTrash() {
  trashMode.value = true
  await loadTrash()
}

function closeTrash() {
  trashMode.value = false
}

async function loadTrash() {
  if (!isTauri()) {
    trashNotes.value = []
    return
  }
  try {
    trashNotes.value = await tauriApi.listTrash()
  } catch (e) {
    console.error('加载垃圾箱失败', e)
  }
}

async function restoreFromTrash(id: number) {
  if (trashBusy.value) return
  trashBusy.value = true
  try {
    await tauriApi.restoreNote(id)
    await Promise.all([loadTrash(), store.refreshNotes()])
  } catch (e) {
    console.error('恢复笔记失败', e)
  } finally {
    trashBusy.value = false
  }
}

async function confirmPurgeNote() {
  const note = purgingNote.value
  purgingNote.value = null
  if (!note || trashBusy.value) return
  trashBusy.value = true
  try {
    await tauriApi.purgeNote(note.id)
    await loadTrash()
  } catch (e) {
    console.error('彻底删除失败', e)
  } finally {
    trashBusy.value = false
  }
}

async function confirmEmptyTrash() {
  emptyTrashConfirm.value = false
  if (trashBusy.value) return
  trashBusy.value = true
  try {
    await tauriApi.emptyTrash()
    await loadTrash()
  } catch (e) {
    console.error('清空垃圾箱失败', e)
  } finally {
    trashBusy.value = false
  }
}

function formatTime(iso: string): string {
  const t = new Date(parseTimestamp(iso))
  const now = new Date()
  const diffMs = now.getTime() - t.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24 && sameDay(now, t)) return `${diffHour} 小时前`
  if (sameYear(now, t)) return `${t.getMonth() + 1}月${t.getDate()}日`
  return `${t.getFullYear()}年${t.getMonth() + 1}月${t.getDate()}日`
}

function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

function sameYear(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear()
}

function summary(n: Note): string {
  return markdownPlainText(n.content, 60) || '空白笔记'
}
</script>

<template>
  <section class="card note-list">
    <header class="nl-header">
      <template v-if="!trashMode">
        <h2 class="nl-title">速记</h2>
        <div class="nl-header-actions">
          <select
            v-model="sortKey"
            class="nl-sort"
            title="排序方式"
            aria-label="排序方式"
          >
            <option value="updated">按修改时间</option>
            <option value="created">按创建时间</option>
            <option value="name">按名称</option>
            <option value="size">按大小</option>
          </select>
          <button
            class="icon-btn trash-entry"
            title="垃圾箱"
            aria-label="打开垃圾箱"
            @click="openTrash"
          >
            <Trash2 :size="15" :stroke-width="2" />
          </button>
          <button class="icon-btn add" title="新建笔记" @click="emit('create')">
            <Plus :size="15" :stroke-width="2.2" />
          </button>
        </div>
      </template>
      <template v-else>
        <h2 class="nl-title">
          <button class="icon-btn back" title="返回列表" aria-label="返回列表" @click="closeTrash">
            <ChevronLeft :size="16" :stroke-width="2.2" />
          </button>
          垃圾箱
        </h2>
        <div class="nl-header-actions">
          <button
            class="icon-btn add"
            :disabled="trashNotes.length === 0"
            title="清空垃圾箱"
            aria-label="清空垃圾箱"
            @click="emptyTrashConfirm = true"
          >
            <Trash2 :size="15" :stroke-width="2" />
          </button>
        </div>
      </template>
    </header>

    <template v-if="!trashMode">
      <!-- 搜索：按名称或内容 -->
      <div class="nl-search">
        <Search :size="13" :stroke-width="2" class="nl-search-icon" aria-hidden="true" />
        <input
          v-model="searchText"
          class="nl-search-input"
          type="text"
          placeholder="搜索标题或内容…"
          aria-label="搜索笔记"
        />
        <button
          v-if="searchText"
          class="nl-search-clear"
          title="清除搜索"
          aria-label="清除搜索"
          @click="searchText = ''"
        >
          <X :size="12" :stroke-width="2.2" />
        </button>
      </div>

      <!-- 标签筛选（自动换行，不再横向溢出） -->
      <nav v-if="store.state.tags.length > 0" class="filter-tabs tag-filter" aria-label="标签筛选">
        <button
          class="filter-tab filter-tab--tag"
          :class="{ active: activeTagId === null }"
          @click="activeTagId = null"
        >
          全部
        </button>
        <button
          v-for="t in store.state.tags"
          :key="t.id"
          class="filter-tab filter-tab--tag"
          :class="{ active: activeTagId === t.id }"
          @click="activeTagId = t.id"
        >
          <span class="tag-name">{{ t.name }}</span>
          <span
            class="tag-x"
            title="删除该标签"
            :aria-label="`删除标签「${t.name}」`"
            @click.stop="removingTag = t"
          >
            <X :size="9" :stroke-width="2.5" />
          </span>
        </button>
      </nav>

      <div v-if="filteredNotes.length > 0" class="nl-body">
        <div
          v-for="n in filteredNotes"
          :key="n.id"
          class="note-item"
          :class="{ active: n.id === activeId }"
          role="button"
          tabindex="0"
          @click="emit('select', n.id)"
          @keydown.enter="emit('select', n.id)"
          @keydown.space.prevent="emit('select', n.id)"
        >
          <div class="note-item-main">
            <span class="note-title" :title="n.title">{{ n.title }}</span>
            <span class="note-meta">{{ formatTime(n.updated_at) }}</span>
            <span class="note-summary" :title="summary(n)">{{ summary(n) }}</span>
          </div>
          <button
            class="icon-btn del"
            title="移入垃圾箱"
            aria-label="移入垃圾箱"
            @click.stop="emit('delete', n.id)"
          >
            <X :size="13" :stroke-width="2" />
          </button>
        </div>
      </div>

      <div v-else class="empty-state">
        <StickyNote :size="24" :stroke-width="1.7" aria-hidden="true" />
        <p v-if="searchText.trim()">没有匹配「{{ searchText.trim() }}」的笔记</p>
        <p v-else>还没有笔记</p>
        <button v-if="!searchText.trim()" class="pill-btn" style="margin-top: 6px" @click="emit('create')">
          新建笔记
        </button>
      </div>
    </template>

    <!-- 垃圾箱视图 -->
    <template v-else>
      <div v-if="trashNotes.length > 0" class="nl-body">
        <div v-for="n in trashNotes" :key="n.id" class="note-item trash-item">
          <div class="note-item-main">
            <span class="note-title" :title="n.title">{{ n.title || '无标题' }}</span>
            <span class="note-meta">删除于 {{ formatTime(n.deleted_at ?? n.updated_at) }}</span>
            <span class="note-summary" :title="summary(n)">{{ summary(n) }}</span>
          </div>
          <div class="trash-actions">
            <button
              class="icon-btn del"
              title="恢复笔记"
              aria-label="恢复笔记"
              @click.stop="restoreFromTrash(n.id)"
            >
              <RotateCcw :size="13" :stroke-width="2" />
            </button>
            <button
              class="icon-btn del"
              title="彻底删除"
              aria-label="彻底删除"
              @click.stop="purgingNote = n"
            >
              <Trash2 :size="13" :stroke-width="2" />
            </button>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <Trash2 :size="24" :stroke-width="1.7" aria-hidden="true" />
        <p>垃圾箱是空的</p>
      </div>
    </template>

    <!-- 删除标签确认 -->
    <ConfirmDialog
      :visible="removingTag != null"
      title="删除标签"
      :message="`「${removingTag?.name ?? ''}」会从所有笔记上摘掉，标签本身也会删除。`"
      hint="这个操作不能撤销。"
      tone="danger"
      confirm-text="删除标签"
      @confirm="confirmRemoveTag"
      @cancel="removingTag = null"
    />

    <!-- 彻底删除单条确认 -->
    <ConfirmDialog
      :visible="purgingNote != null"
      title="彻底删除笔记"
      :message="`「${purgingNote?.title || '无标题'}」将被永久删除。`"
      hint="这个操作不能撤销。"
      tone="danger"
      confirm-text="彻底删除"
      @confirm="confirmPurgeNote"
      @cancel="purgingNote = null"
    />

    <!-- 清空垃圾箱确认 -->
    <ConfirmDialog
      :visible="emptyTrashConfirm"
      title="清空垃圾箱"
      :message="`垃圾箱里的 ${trashNotes.length} 条笔记将被永久删除。`"
      hint="这个操作不能撤销。"
      tone="danger"
      confirm-text="全部删除"
      @confirm="confirmEmptyTrash"
      @cancel="emptyTrashConfirm = false"
    />
  </section>
</template>

<style scoped>
.note-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px 16px;
  min-height: 0;
  /* 速记模块字号：全局基准 × 模块系数 */
  font-size: calc(1rem * var(--fs-notes, 1));
}
.nl-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px;
  margin-bottom: 12px;
}
.nl-title {
  font-size: 1em;
  font-weight: 600;
  color: var(--text-1);
  letter-spacing: -0.01em;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.nl-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.icon-btn.add {
  width: 30px;
  height: 30px;
  background: var(--brand-50);
  color: var(--brand-500);
}
.icon-btn.add:hover {
  background: var(--brand-500);
  color: var(--text-on-accent);
}
.icon-btn.add:disabled {
  opacity: 0.4;
  pointer-events: none;
}
.icon-btn.back {
  width: 26px;
  height: 26px;
}
/* 排序选择：紧凑原生 select，融入头部 */
.nl-sort {
  height: 26px;
  max-width: 92px;
  padding: 0 4px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-2);
  font-size: 0.6875em;
  cursor: pointer;
  outline: none;
}
.nl-sort:hover,
.nl-sort:focus-visible {
  border-color: var(--brand-500);
  color: var(--text-1);
}
.icon-btn.trash-entry {
  width: 30px;
  height: 30px;
  color: var(--text-3);
}
.icon-btn.trash-entry:hover {
  color: var(--c-red);
  background: color-mix(in srgb, var(--c-red) 10%, transparent);
}

/* 搜索框 */
.nl-search {
  position: relative;
  display: flex;
  align-items: center;
  margin: 0 4px 10px;
}
.nl-search-icon {
  position: absolute;
  left: 9px;
  color: var(--text-4);
  pointer-events: none;
}
.nl-search-input {
  width: 100%;
  height: 30px;
  padding: 0 28px 0 28px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-1);
  font-size: 0.75em;
  outline: none;
  transition: border-color 0.15s;
}
.nl-search-input::placeholder {
  color: var(--text-4);
}
.nl-search-input:focus-visible {
  border-color: var(--brand-500);
}
.nl-search-clear {
  position: absolute;
  right: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  color: var(--text-4);
}
.nl-search-clear:hover {
  color: var(--text-1);
  background: var(--bg-card-soft);
}

.nl-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 标签筛选条：换行显示，标签多时全部可见，不再横向溢出 */
.tag-filter {
  padding: 0 4px 8px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.filter-tab--tag .tag-name {
  max-width: 12em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.filter-tab--tag .tag-x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  margin-right: -4px;
  border-radius: 50%;
  opacity: 0;
  color: var(--text-4);
  transition: opacity 0.12s, color 0.12s, background 0.12s;
}
.filter-tab--tag:hover .tag-x,
.filter-tab--tag .tag-x:focus-visible {
  opacity: 1;
}
.filter-tab--tag .tag-x:hover {
  color: var(--c-red);
  background: color-mix(in srgb, var(--c-red) 12%, transparent);
}
.note-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.15s;
}
.note-item:hover {
  background: var(--bg-card-soft);
}
.note-item.active {
  background: var(--brand-50);
}
.note-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 2px;
  background: var(--brand-500);
}
.note-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.note-title {
  font-size: 0.8125em;
  font-weight: 600;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.note-meta {
  font-size: 0.6875em;
  color: var(--text-3);
}
.note-summary {
  font-size: 0.75em;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.del {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  opacity: 0;
  margin-top: -2px;
}
.note-item:hover .del,
.note-item:focus-within .del {
  opacity: 1;
}
.del:hover {
  color: var(--c-red);
  background: color-mix(in srgb, var(--c-red) 10%, transparent);
}

/* 垃圾箱列表项 */
.trash-item {
  cursor: default;
}
.trash-item:hover {
  background: var(--bg-card-soft);
}
.trash-actions {
  display: inline-flex;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  margin-top: -2px;
}
.trash-item:hover .trash-actions,
.trash-item:focus-within .trash-actions {
  opacity: 1;
}
</style>
