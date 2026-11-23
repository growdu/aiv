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
