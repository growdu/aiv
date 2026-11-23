<script setup lang="ts">
// 创作平台的门面。
//
// **写点只有一个**：`drafts/`。保存写草稿箱，过审是另一个动作（复制进母稿层）。
// 身份（站名、品牌名、平台名）**不在源码里**——它们从接口面来。
import { onMounted, ref } from "vue";

import { getJSON, postJSON, putJSON } from "./api/client";
import type { DraftUnit, OutboxSnapshot, ReviewReport } from "./api/types";
import JobLog from "./components/JobLog.vue";
import DocPreview from "./views/DocPreview.vue";
import DraftPicker from "./views/DraftPicker.vue";
import PublishStatus from "./views/PublishStatus.vue";
import ReviewPanel from "./views/ReviewPanel.vue";
import ScriptEditor from "./views/ScriptEditor.vue";
import VideoPreview from "./views/VideoPreview.vue";

const units = ref<DraftUnit[]>([]);
const selected = ref<DraftUnit | null>(null);
const files = ref<Record<string, string>>({});
const message = ref("");
const manualSteps = ref<string[]>([]);
const report = ref<ReviewReport | null>(null);
const reviewing = ref(false);
const jobId = ref<string | null>(null);
const snapshots = ref<OutboxSnapshot[]>([]);


/**
 * 草稿单元 → **母稿层**的坐标。
 *
 * 审校只在母稿层跑（规格 D10），所以审校面板问的是**它过审之后会落在哪**，
 * 不是草稿本身。
 */
function motherSubject(unit: DraftUnit): { kind: string; id: string } | null {
  if (unit.kind === "document") {
    return { kind: "document", id: unit.draft_id };
  }
  if (unit.kind === "episode") {
    // 草稿是 `_video/<分类>/<合集>/<文档>/<档位>`，期路径少一个前缀。
    const parts = unit.draft_id.split("/").filter(Boolean);
    if (parts[0] === "_video") parts.shift();
    return { kind: "episode", id: parts.join("/") };
  }
  return null;
}


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
  await loadReview();
}

/** 拉这一稿的审校报告。**拉不到不是错**——母稿层里还没有它。 */
async function loadReview(): Promise<void> {
  if (!selected.value) return;
  const subject = motherSubject(selected.value);
  report.value = null;
  if (!subject) return;
  reviewing.value = true;
  try {
    const path =
      subject.kind === "document"
        ? "/review/documents/" + subject.id
        : "/review/episodes/" + subject.id;
    report.value = await getJSON<ReviewReport>(path);
  } catch {
    // 母稿层里还没有这一稿（或还没过审）——**不假装有报告**。
    report.value = null;
  } finally {
    reviewing.value = false;
  }
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

/** 出片：**先过审再出片**（规格 D10）——服务端那一步自己会先复制。 */
async function build(): Promise<void> {
  const subject = selected.value ? motherSubject(selected.value) : null;
  if (!subject || subject.kind !== "episode") return;
  const body = await postJSON<{ job_id: string }>(
    "/episodes/" + subject.id + "/build",
  );
  jobId.value = body.job_id;
}

/** 重建：文档内容单元 → 视频内容单元 → 站点。 */
async function rebuild(): Promise<void> {
  const subject = selected.value ? motherSubject(selected.value) : null;
  if (!subject || subject.kind !== "document") return;
  const body = await postJSON<{ job_id: string }>(
    "/documents/" + subject.id + "/rebuild",
  );
  jobId.value = body.job_id;
}

async function loadSnapshots(): Promise<void> {
  try {
    const body = await getJSON<{ snapshots: OutboxSnapshot[] }>("/publish/outbox");
    snapshots.value = body.snapshots ?? [];
  } catch {
    snapshots.value = [];
  }
}

onMounted(() => {
  void loadUnits();
  void loadSnapshots();
});
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

    <ReviewPanel
      :report="report"
      :busy="reviewing"
    />

    <VideoPreview
      v-if="selected && selected.kind === 'episode'"
      :episode="(motherSubject(selected) ?? { id: '' }).id"
      @build="build"
    />

    <DocPreview
      v-if="selected && selected.kind === 'document'"
      :doc-id="(motherSubject(selected) ?? { id: '' }).id"
      @rebuild="rebuild"
    />

    <JobLog :job-id="jobId" />

    <PublishStatus :snapshots="snapshots" />
  </main>
</template>
