<script setup lang="ts">
// 文档预览：iframe 嵌站点的真页面。
//
// **dev server 没跑就不嵌**——给一个永远 404 的 iframe 比不给更坏。
import { onMounted, ref, watch } from "vue";

import { getJSON } from "../api/client";

const props = defineProps<{ docId: string }>();

const emit = defineEmits<{
  (event: "rebuild"): void;
}>();

const url = ref("");
const running = ref(false);
const hint = ref("");

async function load(): Promise<void> {
  if (!props.docId) {
    url.value = "";
    return;
  }
  try {
    const body = await getJSON<{ url: string; running: boolean; hint: string }>(
      "/documents/" + props.docId + "/preview",
    );
    url.value = body.url ?? "";
    running.value = Boolean(body.running);
    hint.value = body.hint ?? "";
  } catch {
    url.value = "";
    running.value = false;
    hint.value = "这一篇还没有预览地址。";
  }
}

onMounted(load);
watch(() => props.docId, load);
</script>

<template>
  <section class="preview">
    <header class="preview__head">
      <h2>预览</h2>
      <button data-test="rebuild" type="button" @click="emit('rebuild')">
        重建
      </button>
    </header>

    <iframe
      v-if="running && url"
      data-test="frame"
      :src="url"
      title="文档预览"
    />
    <p v-else data-test="hint">{{ hint || "预览服务没跑起来。" }}</p>
  </section>
</template>

<style scoped>
.preview {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-2);
  box-shadow: var(--shadow-1);
  padding: var(--sp-4) var(--sp-5);
}

.preview__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}

.preview__head h2 {
  font-size: var(--fs-4);
}

/* 站点页面嵌进来——给它一块白底和边框，像一张纸。 */
.preview iframe {
  width: 100%;
  height: 70vh;
  min-height: 360px;
  border: 1px solid var(--border);
  border-radius: var(--r-1);
  background: var(--surface);
}

.preview p {
  padding: var(--sp-5);
  background: var(--surface-2);
  border-radius: var(--r-1);
  color: var(--text-3);
  font-size: var(--fs-2);
  text-align: center;
}
</style>
