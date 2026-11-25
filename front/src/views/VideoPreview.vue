<script setup lang="ts">
// 成片与中间大产物。
//
// **产物 URL 是接口的地址**，不是文件系统路径——前端不许自己拼路径。
import { onMounted, ref, watch } from "vue";

import { artifactURL, getJSON } from "../api/client";
import type { Artifact } from "../api/types";

const props = defineProps<{ episode: string }>();

const emit = defineEmits<{
  (event: "build"): void;
}>();

const artifacts = ref<Artifact[]>([]);
const message = ref("");

async function load(): Promise<void> {
  if (!props.episode) {
    artifacts.value = [];
    return;
  }
  try {
    const body = await getJSON<{ artifacts: Artifact[] }>(
      "/episodes/" + props.episode + "/artifacts",
    );
    artifacts.value = body.artifacts ?? [];
    message.value = "";
  } catch {
    artifacts.value = [];
    message.value = "这一期还没有产物——先出片。";
  }
}

onMounted(load);
watch(() => props.episode, load);
</script>

<template>
  <section class="preview">
    <header class="preview__head">
      <h2>产物</h2>
      <button data-test="build" type="button" @click="emit('build')">
        出片
      </button>
    </header>

    <p v-if="message" data-test="message">{{ message }}</p>

    <div v-for="artifact in artifacts" :key="artifact.artifact_id" class="preview__item">
      <video
        v-if="artifact.kind === 'cut'"
        controls
        :src="artifactURL(artifact.artifact_id)"
      />
      <audio
        v-else-if="artifact.kind === 'narration'"
        controls
        :src="artifactURL(artifact.artifact_id)"
      />
      <img
        v-else-if="artifact.kind === 'frame'"
        :src="artifactURL(artifact.artifact_id)"
        :alt="artifact.name"
      />
      <a
        v-else
        :href="artifactURL(artifact.artifact_id)"
        :data-test="`artifact-${artifact.artifact_id}`"
      >
        {{ artifact.name }}
      </a>
      <span class="preview__size">{{ artifact.bytes }} 字节</span>
    </div>
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

.preview p {
  color: var(--text-3);
  font-size: var(--fs-2);
  margin-bottom: var(--sp-2);
}

/* 一个产物一块地——视频、音频、帧、链接各归各的。 */
.preview__item {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  padding: var(--sp-3) 0;
  border-top: 1px solid var(--border);
}

.preview__item video {
  width: 100%;
  max-width: 480px;
  border-radius: var(--r-1);
  background: var(--surface-3);
}

.preview__item audio {
  width: 100%;
  max-width: 480px;
}

.preview__item img {
  max-width: 320px;
  border-radius: var(--r-1);
  border: 1px solid var(--border);
}

.preview__size {
  color: var(--text-3);
  font-size: var(--fs-1);
  font-variant-numeric: tabular-nums;
}
</style>
