<script setup lang="ts">
// 草稿箱列表：**平台唯一的入口**。
//
// 这里只列草稿单元，不列母稿层的东西——母稿层的内容不归这里改。
import { computed, ref } from "vue";

import type { DraftUnit } from "../api/types";

const props = defineProps<{ units: DraftUnit[]; selected?: string | null }>();

const emit = defineEmits<{
  (event: "select", draftId: string): void;
  (event: "create", kind: string): void;
  (event: "draft"): void;
}>();

/** 搜索框里的字。 */
const query = ref("");

/** 分组的次序：先文档线，后视频线。 */
const KIND_ORDER = ["document", "index", "bundle", "skeleton", "episode"];

/** 每种形态在界面上叫什么。 */
const KIND_TITLES: Record<string, string> = {
  document: "文档稿",
  index: "索引页",
  bundle: "合集稿",
  skeleton: "骨架",
  episode: "视频期",
};

const groups = computed(() => {
  const needle = query.value.trim();
  const matched = props.units.filter(
    (unit) => !needle || unit.draft_id.includes(needle),
  );
  const byKind = new Map<string, DraftUnit[]>();
  for (const unit of matched) {
    const bucket = byKind.get(unit.kind);
    if (bucket) bucket.push(unit);
    else byKind.set(unit.kind, [unit]);
  }
  const out: { kind: string; title: string; units: DraftUnit[] }[] = [];
  for (const kind of KIND_ORDER) {
    const bucket = byKind.get(kind);
    if (bucket?.length) {
      out.push({ kind, title: KIND_TITLES[kind] ?? kind, units: bucket });
      byKind.delete(kind);
    }
  }
  for (const [kind, bucket] of byKind) {
    out.push({ kind, title: KIND_TITLES[kind] ?? kind, units: bucket });
  }
  return out;
});
</script>

<template>
  <section class="picker">
    <header class="picker__head">
      <input
        v-model="query"
        data-test="search"
        type="search"
        placeholder="按草稿号过滤"
      />
      <button
        class="btn--primary"
        data-test="create-document"
        type="button"
        @click="emit('create', 'document')"
      >
        新建文档草稿
      </button>
      <button
        data-test="create-episode"
        type="button"
        @click="emit('create', 'episode')"
      >
        新建视频草稿
      </button>
      <!-- **AI 起草这一版没做**（规格 §二 N2）——按钮在位，
           点了把后端的原话报出来，不假装能做。 -->
      <button
        class="btn--ghost"
        data-test="ai-draft"
        type="button"
        @click="emit('draft')"
      >
        起草（未启用）
      </button>
    </header>

    <p v-if="!groups.length" data-test="empty">草稿箱里还没有东西。</p>

    <div v-for="group in groups" :key="group.kind" class="picker__group">
      <h3>{{ group.title }}</h3>
      <ul>
        <li v-for="unit in group.units" :key="unit.draft_id">
          <button
            type="button"
            :class="{ 'picker__item--active': unit.draft_id === props.selected }"
            :data-test="`unit-${unit.draft_id}`"
            @click="emit('select', unit.draft_id)"
          >
            {{ unit.draft_id }}
          </button>
          <!-- 索引页与合集稿**不过审**：原因挂在行上，不刷一整屏。 -->
          <span
            v-if="!unit.promotable"
            class="picker__reason"
            :title="unit.reason"
          >
            {{ unit.reason }}
          </span>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.picker {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.picker__head {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.picker__head input[type="search"] {
  font-size: var(--fs-2);
}

.picker__head button {
  width: 100%;
  font-size: var(--fs-2);
}

.picker__group {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

/* 分组标题：小写、淡、窄——它是路标，不是标题。 */
.picker__group h3 {
  font-size: var(--fs-1);
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--text-3);
  text-transform: uppercase;
}

.picker__group ul {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.picker__group li {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* 一行稿子：左边一截路径，右边一个状态点。 */
.picker__group button {
  width: 100%;
  text-align: left;
  background: transparent;
  border-color: transparent;
  font-family: var(--font-mono);
  font-size: var(--fs-1);
  color: var(--text-2);
  padding: 5px var(--sp-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker__group button:hover:not(:disabled) {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent-hover);
}

/* 当前选中的那一行——一眼看得见。 */
.picker__group button.picker__item--active {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent-hover);
  font-weight: 600;
}

/* 不过审的原因：**默认收起来**——一屏索引页各挂一句同样的理由太吵。
 * 悬停或选中那一行时才展开，完整的话也在 title 里。 */
.picker__reason {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  padding-left: var(--sp-2);
  color: var(--text-3);
  font-size: var(--fs-1);
  white-space: nowrap;
  transition: max-height 0.15s ease, opacity 0.15s ease;
}

.picker__group li:hover .picker__reason,
.picker__group li:has(.picker__item--active) .picker__reason {
  max-height: 2em;
  opacity: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
