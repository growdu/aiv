<script setup lang="ts">
// 编辑器：**保存只写草稿箱**（规格 §7.2 铁律 1）。
//
// 这里**没有**写母稿层的入口——母稿层的内容不归这里改。
// 「过审」是另一个按钮，它做的是**复制**（规格 D9）。
import { computed, reactive, watch } from "vue";

import type { DraftUnit } from "../api/types";

const props = defineProps<{
  unit: DraftUnit;
  files: Record<string, string>;
}>();

const emit = defineEmits<{
  (event: "save", files: Record<string, string>): void;
  (event: "promote"): void;
}>();

/** 本地编辑副本——**只在这里改**，没点保存就什么都不写。 */
const buffer = reactive<Record<string, string>>({});

watch(
  () => props.files,
  (files) => {
    for (const key of Object.keys(buffer)) delete buffer[key];
    for (const [name, text] of Object.entries(files ?? {})) {
      buffer[name] = text;
    }
  },
  { immediate: true, deep: true },
);

/** 文件名 → 一行说明。**两个同名不同义的 `episode` 字段必须分开摆**（规格 §7.4）。 */
const NOTES: Record<string, string> = {
  "口播稿.md": "这一份的 episode 记的是**文档路径**（三层：分类/合集/文档）",
  "contract.json": "这一份的 episode 记的是**期路径**（四层：分类/合集/文档/档位）",
  "publish.json": "这一份的 episode 与契约里的**逐字相等**（同一个身份）",
};

const names = computed(() => Object.keys(props.files ?? {}));

function noteFor(name: string): string {
  return NOTES[name] ?? "";
}

function onSave(): void {
  emit("save", { ...buffer });
}
</script>

<template>
  <section class="editor">
    <header class="editor__head">
      <h2>{{ unit.draft_id }}</h2>
      <span class="editor__kind">{{ unit.kind }}</span>
    </header>

    <p v-for="name in names" :key="`note-${name}`" class="editor__note">
      {{ noteFor(name) }}
    </p>

    <div v-for="name in names" :key="name" class="editor__file">
      <h4>{{ name }}</h4>
      <textarea
        :data-test="`file-${name}`"
        v-model="buffer[name]"
        rows="14"
        spellcheck="false"
      />
    </div>

    <footer class="editor__foot">
      <button data-test="save" type="button" @click="onSave">存进草稿箱</button>
      <!-- 索引页与合集稿**不过审**——按钮压根不渲染。 -->
      <button
        v-if="unit.promotable"
        data-test="promote"
        type="button"
        @click="emit('promote')"
      >
        过审（复制到母稿层）
      </button>
      <span v-else class="editor__reason">{{ unit.reason }}</span>
    </footer>
  </section>
</template>
