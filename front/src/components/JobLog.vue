<script setup lang="ts">
// 作业日志：SSE 实时推，出错就退回拉一次全量。
//
// **退出码是原始的，标签是尽力而为的**（规格 §六）——两者都摆出来，
// 别拿标签冒充退出码。
import { onBeforeUnmount, ref, watch } from "vue";

import { eventURL, getJSON } from "../api/client";
import type { Job } from "../api/types";

const props = defineProps<{ jobId: string | null }>();

const job = ref<Job | null>(null);
const lines = ref<string[]>([]);

let source: EventSource | null = null;

function close(): void {
  if (source) {
    source.close();
    source = null;
  }
}

/** SSE 断了就退回拉一次全量——**日志不许丢**。 */
async function pullAll(): Promise<void> {
  if (!props.jobId) return;
  try {
    const body = await getJSON<Job>("/jobs/" + props.jobId);
    job.value = body;
    lines.value = [...(body.log ?? [])];
  } catch {
    // 作业没找到——**不编一个状态出来**。
    job.value = null;
  }
}

watch(
  () => props.jobId,
  async (jobId) => {
    close();
    lines.value = [];
    job.value = null;
    if (!jobId) return;

    try {
      source = new EventSource(eventURL(jobId));
      source.onmessage = (event) => {
        let payload: any = null;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }
        if (payload?.type === "log") {
          lines.value = [...lines.value, String(payload.text ?? "")];
        } else if (payload?.type === "done") {
          job.value = {
            ...(job.value ?? ({} as Job)),
            id: jobId,
            kind: job.value?.kind ?? "",
            status: payload.status ?? "unknown",
            exit_code: payload.exit_code ?? null,
            exit_label: payload.exit_label ?? "unknown",
            started_at: job.value?.started_at ?? "",
            finished_at: job.value?.finished_at ?? null,
            log: lines.value,
          };
          close();
        }
      };
      source.onerror = () => {
        close();
        void pullAll();
      };
    } catch {
      await pullAll();
    }
  },
  { immediate: true },
);

onBeforeUnmount(close);
</script>

<template>
  <section class="job">
    <h2>作业</h2>

    <p v-if="!jobId" data-test="empty">还没有作业。</p>

    <template v-else>
      <p v-if="job" data-test="status">
        {{ job.status }}
        <span v-if="job.exit_code !== null" data-test="exit">
          退出码 {{ job.exit_code }}（{{ job.exit_label }}）
        </span>
      </p>
      <pre data-test="log">{{ lines.join("\n") }}</pre>
    </template>
  </section>
</template>
