<script setup lang="ts">
// 新建草稿的表单：**坐标由目录树驱动**。
//
// 目录即接口——树的深度是仓库的深度（源向线比扁平稿深两级），
// 所以这里一层一层往下走：树里还有子目录就多一级，没有了就停下填期号。
//
// **不 import 任何后端模块**——选项从 `GET /api/drafts/options` 来。
import { computed, ref } from "vue";

import type { CoordinateNode, DraftOptions } from "../api/types";

const props = defineProps<{
  kind: "document" | "episode";
  options: DraftOptions;
}>();

const emit = defineEmits<{
  (
    event: "submit",
    payload: { kind: string; draft_id: string; title: string },
  ): void;
  (event: "cancel"): void;
}>();

/** 下拉里那一项的哨兵值——「手填一级」。 */
const NEW = "__new__";

/** 已选的目录层。 */
const levels = ref<string[]>([]);
/** 每一层是不是手填的（手填的层底下没有子目录可走）。 */
const manual = ref<boolean[]>([]);

/** 期号（文档流）/ 标题。 */
const slug = ref("");
const title = ref("");
/** 档位（视频流）——固定的三档。 */
const tier = ref(props.options.episode.tiers[0] ?? "");

/** 文档流的层名：分类 → 二级内容 → …… */
const DOCUMENT_LEVELS = ["分类", "二级内容", "三级内容", "四级内容"];
/** 视频流的层名：期路径的前三层。 */
const EPISODE_LEVELS = ["系列", "合集", "文档"];

/** 走树：已选的那几层下面还有什么。 */
function childrenAt(level: number): string[] {
  let nodes: CoordinateNode[] =
    props.kind === "episode"
      ? props.options.episode.series
      : props.options.document.categories;
  for (let i = 0; i < level; i++) {
    // 手填的一层底下没有子目录可走。
    if (manual.value[i]) return [];
    const node = nodes.find((n) => n.name === levels.value[i]);
    if (!node) return [];
    nodes = node.children;
  }
  return nodes.map((n) => n.name);
}

/** 要渲染几级目录。 */
const levelCount = computed(() => {
  // 期路径是四层（系列/合集/文档/档位）——档位是固定的，不占目录层。
  if (props.kind === "episode") return EPISODE_LEVELS.length;
  const chosen = levels.value.length;
  // 文档至少两级目录（分类 / 二级内容），树里还有就再往下走一层。
  if (chosen < 2) return chosen + 1;
  return childrenAt(chosen).length > 0 ? chosen + 1 : chosen;
});

const levelIndexes = computed(() =>
  Array.from({ length: levelCount.value }, (_, i) => i),
);

function levelLabel(index: number): string {
  const names = props.kind === "episode" ? EPISODE_LEVELS : DOCUMENT_LEVELS;
  return names[index] ?? `第 ${index + 1} 层`;
}

/** 选下拉里的一项——手填就把那一层换成文本框。 */
function setLevel(level: number, value: string): void {
  levels.value = levels.value.slice(0, level);
  manual.value = manual.value.slice(0, level);
  manual.value[level] = value === NEW;
  levels.value[level] = value === NEW ? "" : value;
}

/** 手填某一层。 */
function setManualLevel(level: number, value: string): void {
  levels.value = levels.value.slice(0, level);
  manual.value = manual.value.slice(0, level);
  manual.value[level] = true;
  levels.value[level] = value;
}

/** 拼出来的坐标。 */
const draftId = computed(() => {
  const parts = levels.value.map((part) => part.trim());
  if (parts.some((part) => part.length === 0)) return "";
  if (props.kind === "episode") {
    return tier.value ? ["_video", ...parts, tier.value].join("/") : "";
  }
  return slug.value.trim() ? [...parts, slug.value.trim()].join("/") : "";
});

/** 填全了才许提交。 */
const valid = computed(() => {
  if (levels.value.length !== levelCount.value) return false;
  if (!levels.value.every((part) => part.trim().length > 0)) return false;
  return props.kind === "episode" ? tier.value.length > 0 : slug.value.trim().length > 0;
});

function submit(): void {
  if (!valid.value) return;
  emit("submit", {
    kind: props.kind,
    draft_id: draftId.value,
    title: title.value.trim(),
  });
}
</script>

<template>
  <section class="new-draft">
    <h2>{{ kind === "episode" ? "新建视频草稿" : "新建文档草稿" }}</h2>

    <!-- **开一级目录 = 新增一个对外可见的分类**——这是策展动作，
         不是随手填个名字。规矩见 drafts/README.md §一。 -->
    <p class="new-draft__note" data-test="note">
      新开一级目录 = 新增一个分类或一块二级内容——按 drafts/README.md §一，
      这是策展动作，先想清楚。
    </p>

    <label v-for="i in levelIndexes" :key="i" class="new-draft__level">
      <span>{{ levelLabel(i) }}</span>
      <select
        v-if="!manual[i] && childrenAt(i).length"
        :data-test="`select-level-${i}`"
        :value="levels[i] ?? ''"
        @change="setLevel(i, ($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>选一个…</option>
        <option v-for="name in childrenAt(i)" :key="name" :value="name">
          {{ name }}
        </option>
        <option :value="NEW">＋ 新建一级…</option>
      </select>
      <input
        v-else
        :data-test="`input-level-${i}`"
        type="text"
        :value="levels[i] ?? ''"
        @input="setManualLevel(i, ($event.target as HTMLInputElement).value)"
      />
    </label>

    <label v-if="kind === 'episode'" class="new-draft__level">
      <span>档位</span>
      <select data-test="select-tier" v-model="tier">
        <option v-for="t in options.episode.tiers" :key="t" :value="t">{{ t }}</option>
      </select>
    </label>
    <label v-else class="new-draft__level">
      <span>期号</span>
      <input data-test="input-slug" type="text" v-model="slug" />
    </label>

    <label class="new-draft__level">
      <span>标题</span>
      <input data-test="input-title" type="text" v-model="title" />
    </label>

    <p v-if="draftId" data-test="preview">drafts/{{ draftId }}</p>

    <button data-test="submit" type="button" :disabled="!valid" @click="submit">
      创建
    </button>
    <button data-test="cancel" type="button" @click="emit('cancel')">取消</button>
  </section>
</template>
