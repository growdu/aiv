<script setup lang="ts">
// 创作平台的门面。
//
// **写点只有一个**：`drafts/`。保存写草稿箱，过审是另一个动作（复制进母稿层）。
// 身份（站名、品牌名、平台名）**不在源码里**——它们从接口面来。
import { onMounted, ref } from "vue";

import { getJSON, postJSON, putJSON } from "./api/client";
import type { DraftUnit } from "./api/types";
import DraftPicker from "./views/DraftPicker.vue";
import ScriptEditor from "./views/ScriptEditor.vue";

const units = ref<DraftUnit[]>([]);
const selected = ref<DraftUnit | null>(null);
const files = ref<Record<string, string>>({});
const message = ref("");
const manualSteps = ref<string[]>([]);

async function loadUnits(): Promise<void> {
  const body = await getJSON<{ units: DraftUnit[] }>("/drafts");
  units.value = body.units;
}

async function select(draftId: string): Promise<void> {
  const body = await getJSON<DraftUnit & { contents: Record<string, string> }>(
    "/drafts/" + draftId,
  );
  selected.value = body;
  files.value = body.contents ?? {};
  message.value = "";
  manualSteps.value = [];
}

async function save(payload: Record<string, string>): Promise<void> {
  if (!selected.value) return;
  await putJSON("/drafts/" + selected.value.draft_id, { files: payload });
  message.value = "已存进草稿箱。";
}

async function promote(): Promise<void> {
  if (!selected.value) return;
  const body = await postJSON<{ manual_steps: string[] }>(
    "/drafts/" + selected.value.draft_id + "/promote",
  );
  message.value = "已复制到母稿层。还欠你三步：";
  manualSteps.value = body.manual_steps ?? [];
}

async function create(kind: string): Promise<void> {
  message.value = "新建要在服务端定路径——这一版的界面还没接新建表单。";
  void kind;
}

onMounted(loadUnits);
</script>

<template>
  <main>
    <h1>创作平台</h1>

    <DraftPicker
      :units="units"
      @select="select"
      @create="create"
    />

    <p v-if="message" data-test="message">{{ message }}</p>
    <ol v-if="manualSteps.length" data-test="manual-steps">
      <li v-for="step in manualSteps" :key="step">{{ step }}</li>
    </ol>

    <ScriptEditor
      v-if="selected"
      :unit="selected"
      :files="files"
      @save="save"
      @promote="promote"
    />
  </main>
</template>
