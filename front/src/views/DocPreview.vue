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
