<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Plus, StickyNote, X } from 'lucide-vue-next'
import type { Note, Tag } from '../api/tauri'
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

const sortedNotes = computed(() => {
  const list = [...props.notes].sort(
    (a, b) => parseTimestamp(b.updated_at) - parseTimestamp(a.updated_at),
  )
  if (activeTagId.value === null) return list
  return list.filter((n) => tagMap.value.get(n.id)?.includes(activeTagId.value!))
})

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
      <h2 class="nl-title">速记</h2>
      <button class="icon-btn add" title="新建笔记" @click="emit('create')">
        <Plus :size="15" :stroke-width="2.2" />
      </button>
    </header>

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

    <div v-if="sortedNotes.length > 0" class="nl-body">
      <div
        v-for="n in sortedNotes"
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
          title="删除笔记"
          aria-label="删除笔记"
          @click.stop="emit('delete', n.id)"
        >
          <X :size="13" :stroke-width="2" />
        </button>
      </div>
    </div>

    <div v-else class="empty-state">
      <StickyNote :size="24" :stroke-width="1.7" aria-hidden="true" />
      <p>还没有笔记</p>
      <button class="pill-btn" style="margin-top: 6px" @click="emit('create')">
        新建笔记
      </button>
    </div>
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
</style>
