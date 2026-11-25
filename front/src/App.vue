<script setup lang="ts">
// 创作平台的门面。
//
// **写点只有一个**：`drafts/`。保存写草稿箱，过审是另一个动作（复制进母稿层）。
// 身份（站名、品牌名、平台名）**不在源码里**——它们从接口面来。
import { onMounted, ref } from "vue";

import { ApiError, getJSON, postJSON, putJSON } from "./api/client";
import type { DraftOptions, DraftUnit, OutboxSnapshot, ReviewReport } from "./api/types";
import JobLog from "./components/JobLog.vue";
import DocPreview from "./views/DocPreview.vue";
import DraftPicker from "./views/DraftPicker.vue";
import NewDraftForm from "./views/NewDraftForm.vue";
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
/** 坐标选项（目录树）——建草稿的表单要靠它。 */
const options = ref<DraftOptions | null>(null);
/** 开着的新建表单：空 = 不开。 */
const newKind = ref<"document" | "episode" | null>(null);


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
  message.value = "";
  try {
    options.value = await getJSON<DraftOptions>("/drafts/options");
  } catch (err) {
    message.value = errorText(err);
    return;
  }
  newKind.value = kind === "episode" ? "episode" : "document";
}

/** 建好了：刷新列表，**并自动选中**新的一稿。 */
async function submitDraft(payload: {
  kind: string;
  draft_id: string;
  title: string;
}): Promise<void> {
  try {
    await postJSON("/drafts", payload);
  } catch (err) {
    // 建不出来 → 把后端的话报出来，**不假装成功**。
    message.value = errorText(err);
    return;
  }
  newKind.value = null;
  message.value = "建好了：" + payload.draft_id;
  await loadUnits();
  await select(payload.draft_id);
}

/** AI 起草——**这一版没做**（规格 §二 N2）。按钮在位，点了报后端的原话。 */
async function aiDraft(): Promise<void> {
  try {
    await postJSON("/drafts/draft");
    message.value = "起草成功了。";
  } catch (err) {
    message.value = errorText(err);
  }
}

/** 后端说的话。 */
function errorText(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  return err instanceof Error ? err.message : String(err);
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
  <div class="shell">
    <!-- 顶栏：只是门面的名字，不是站名——身份在缝里。 -->
    <header class="shell__bar">
      <h1 class="shell__title">创作平台</h1>
      <p class="shell__sub">草稿箱 · 审校 · 产物 · 出包</p>
    </header>

    <!-- 一条消息占满一整行——出错时它得在哪儿都看得见。 -->
    <p v-if="message" class="flash" data-test="message">{{ message }}</p>

    <div class="shell__body">
      <aside class="shell__side" data-test="side">
        <DraftPicker
          :units="units"
          :selected="selected?.draft_id ?? null"
          @select="select"
          @create="create"
          @draft="aiDraft"
        />
      </aside>

      <main class="shell__main" data-test="main">
        <ol v-if="manualSteps.length" class="steps" data-test="manual-steps">
          <li v-for="step in manualSteps" :key="step">{{ step }}</li>
        </ol>

        <NewDraftForm
          v-if="newKind && options"
          :kind="newKind"
          :options="options"
          @submit="submitDraft"
          @cancel="newKind = null"
        />

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
    </div>
  </div>
</template>

<style scoped>
/* 工作台：**两栏**。
 *
 * 左栏是草稿箱（平台的入口），右栏是这一稿的内容。
 * 窄屏时两栏叠起来——手机上先看稿子。
 */
.shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.shell__bar {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-5);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.shell__title {
  font-size: var(--fs-5);
  letter-spacing: 0.01em;
}

.shell__sub {
  color: var(--text-3);
  font-size: var(--fs-1);
}

/* 一条消息 */
.flash {
  padding: var(--sp-2) var(--sp-5);
  background: var(--accent-soft);
  border-bottom: 1px solid var(--accent-border);
  color: var(--accent-hover);
  font-size: var(--fs-2);
}

.shell__body {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  align-items: start;
  flex: 1;
}

.shell__side {
  position: sticky;
  top: 0;
  align-self: start;
  max-height: 100vh;
  overflow-y: auto;
  padding: var(--sp-4);
  background: var(--surface);
  border-right: 1px solid var(--border);
}

.shell__main {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  padding: var(--sp-5);
  min-width: 0;
}

/* 欠你的手工步骤——一份待办清单。 */
.steps {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  padding: var(--sp-3) var(--sp-4) var(--sp-3) var(--sp-6);
  background: var(--warn-soft);
  border: 1px solid #f0dcc0;
  border-radius: var(--r-2);
  color: var(--warn);
  font-size: var(--fs-2);
}

.steps li {
  list-style: decimal;
}

@media (max-width: 900px) {
  .shell__body {
    grid-template-columns: minmax(0, 1fr);
  }

  .shell__side {
    position: static;
    max-height: none;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
}
</style>
