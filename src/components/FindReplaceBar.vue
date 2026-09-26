<script setup lang="ts">
/** 编辑器查找替换浮条：纯 UI + 状态回传，匹配/跳转/替换逻辑由父级按模式路由
 *  （wysiwyg 走 ProseMirror 事务，源码/分屏走 CodeMirror search API）。 */
import { nextTick, ref, watch } from 'vue'
import { ChevronUp, ChevronDown, CaseSensitive, Replace, ReplaceAll, X, Regex } from 'lucide-vue-next'

const props = defineProps<{
  visible: boolean
  withReplace: boolean
  total: number
  current: number
}>()

const emit = defineEmits<{
  (e: 'update:search', v: string): void
  (e: 'update:replace', v: string): void
  (e: 'update:case', v: boolean): void
  (e: 'update:regexp', v: boolean): void
  (e: 'next'): void
  (e: 'prev'): void
  (e: 'replace-one'): void
  (e: 'replace-all'): void
  (e: 'close'): void
}>()

const searchText = ref('')
const replaceText = ref('')
const caseSensitive = ref(false)
const useRegex = ref(false)
const searchInput = ref<HTMLInputElement | null>(null)

watch(
  () => props.visible,
  async (v) => {
    if (!v) return
    await nextTick()
    searchInput.value?.focus()
    searchInput.value?.select()
  },
)

function onSearchInput() {
  emit('update:search', searchText.value)
}
function onReplaceInput() {
  emit('update:replace', replaceText.value)
}
function onSearchKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    if (e.shiftKey) emit('prev')
    else emit('next')
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}
function toggleCase() {
  caseSensitive.value = !caseSensitive.value
  emit('update:case', caseSensitive.value)
}
function toggleRegex() {
  useRegex.value = !useRegex.value
  emit('update:regexp', useRegex.value)
}

/** 计数展示：无查询时空白，无结果显「无」 */
const countText = () => (searchText.value ? (props.total ? `${props.current}/${props.total}` : '无') : '')
</script>

<template>
  <Transition name="find-bar">
    <div v-if="visible" class="find-bar" role="search" @keydown.stop>
      <div class="find-row">
        <input
          ref="searchInput"
          v-model="searchText"
          class="find-input"
          type="text"
          placeholder="查找…"
          spellcheck="false"
          @input="onSearchInput"
          @keydown="onSearchKeydown"
        />
        <span class="find-count" :class="{ none: searchText && !total }">{{ countText() }}</span>
        <button class="find-btn" title="上一个 (Shift+Enter)" @click="emit('prev')">
          <ChevronUp :size="14" :stroke-width="2" />
        </button>
        <button class="find-btn" title="下一个 (Enter)" @click="emit('next')">
          <ChevronDown :size="14" :stroke-width="2" />
        </button>
        <button
          class="find-btn"
          :class="{ active: caseSensitive }"
          title="区分大小写"
          @click="toggleCase"
        >
          <CaseSensitive :size="14" :stroke-width="2" />
        </button>
        <button
          class="find-btn"
          :class="{ active: useRegex }"
          title="正则表达式"
          @click="toggleRegex"
        >
          <Regex :size="14" :stroke-width="2" />
        </button>
        <button class="find-btn close" title="关闭 (Esc)" @click="emit('close')">
          <X :size="14" :stroke-width="2" />
        </button>
      </div>
      <div v-if="withReplace" class="find-row replace-row">
        <input
          v-model="replaceText"
          class="find-input"
          type="text"
          placeholder="替换为…"
          spellcheck="false"
          @input="onReplaceInput"
          @keydown.enter.prevent="emit('replace-one')"
        />
        <button class="find-btn" title="替换" :disabled="!searchText" @click="emit('replace-one')">
          <Replace :size="14" :stroke-width="2" />
        </button>
        <button class="find-btn" title="全部替换" :disabled="!searchText" @click="emit('replace-all')">
          <ReplaceAll :size="14" :stroke-width="2" />
        </button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.find-bar {
  position: absolute;
  top: 8px;
  right: 16px;
  z-index: 60;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg, 12px);
  background: var(--bg-card-solid);
  backdrop-filter: blur(18px) saturate(1.4);
  -webkit-backdrop-filter: blur(18px) saturate(1.4);
  box-shadow: 0 8px 28px rgba(30, 30, 60, 0.16);
}
.find-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.find-input {
  width: 150px;
  height: 26px;
  padding: 0 8px;
  font-size: 12px;
  color: var(--text-1);
  background: var(--input-bg);
  border: 1px solid var(--border-soft);
  border-radius: 7px;
  outline: none;
}
.find-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--brand-glow);
}
.find-count {
  min-width: 44px;
  text-align: center;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--text-3);
}
.find-count.none {
  color: var(--c-orange);
}
.find-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--text-2);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
.find-btn:hover {
  background: var(--brand-50);
  color: var(--text-1);
}
.find-btn.active {
  background: var(--brand-500);
  color: var(--text-on-accent);
}
.find-btn:disabled {
  opacity: 0.4;
  cursor: default;
}
.find-btn.close:hover {
  background: var(--c-red);
  color: #fff;
}
.find-bar-enter-active,
.find-bar-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}
.find-bar-enter-from,
.find-bar-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
