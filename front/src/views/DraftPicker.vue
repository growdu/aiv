<script setup lang="ts">
// 草稿箱列表：**平台唯一的入口**。
//
// 这里只列草稿单元，不列母稿层的东西——母稿层的内容不归这里改。
import { computed, ref } from "vue";

import type { DraftUnit } from "../api/types";

const props = defineProps<{ units: DraftUnit[] }>();

const emit = defineEmits<{
  (event: "select", draftId: string): void;
  (event: "create", kind: string): void;
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
    </header>

    <p v-if="!groups.length" data-test="empty">草稿箱里还没有东西。</p>

    <div v-for="group in groups" :key="group.kind" class="picker__group">
      <h3>{{ group.title }}</h3>
      <ul>
        <li v-for="unit in group.units" :key="unit.draft_id">
          <button
            type="button"
            :data-test="`unit-${unit.draft_id}`"
            @click="emit('select', unit.draft_id)"
          >
            {{ unit.draft_id }}
          </button>
          <!-- 索引页与合集稿**不过审**：把原因摆在行里。 -->
          <span v-if="!unit.promotable" class="picker__reason">
            {{ unit.reason }}
          </span>
        </li>
      </ul>
    </div>
  </section>
</template>
