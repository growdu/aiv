/** 接口面的类型——与 `api/` 端出来的 JSON 一一对应。
 *
 * **这里只描述形状，不放值**：站名、品牌名、平台名一个都没有。
 * 它们在缝里，接口面会送来（`GET /api/config`、`GET /api/platforms`）。
 */

export type Severity = "error" | "warn" | "info";

export interface Signal {
  rule: string;
  layer: string;
  severity: Severity;
  target: string;
  line: number | null;
  excerpt: string;
  detail: string;
}

export interface Gate {
  status: string;
  blocking: boolean;
  reason: string;
}

export interface ReviewReport {
  subject: { kind: string; id: string; path: string };
  layer: string;
  counts: { error: number; warn: number; info: number };
  signals: Signal[];
  notes: string[];
  gate: Gate;
}

export interface DraftUnit {
  kind: string;
  draft_id: string;
  path: string;
  files: string[];
  promotable: boolean;
  reason: string;
}

export interface Job {
  id: string;
  kind: string;
  status: string;
  exit_code: number | null;
  exit_label: string;
  started_at: string;
  finished_at: string | null;
  log: string[];
}

export interface Artifact {
  artifact_id: string;
  name: string;
  kind: string;
  bytes: number;
}

export interface PlatformCapability {
  id: string;
  name: string;
  kind: string;
  automation: string;
  tiers: string[];
  limits: Record<string, number>;
  spec: unknown;
}

/**
 * 出包快照的**公共子集**。
 *
 * 各平台的快照键数不一样——这里只列公共的那几个，
 * **缺了的键就缺着**（接口面不补默认值）。
 */
export interface OutboxSnapshot {
  platform: string;
  status: string;
  reason?: string;
  updated_at?: string;
  content_id?: string;
  title?: string;
  published_url?: string;
}

/** 一篇母稿（`docs/` 里的）。 */
export interface DocumentMeta {
  id: string;
  path: string;
  title: string;
}

/** 一期视频（`video/episodes/` 里的四层目录）。 */
export interface EpisodeMeta {
  episode: string;
  doc: string;
  tier: string;
  title: string;
}

/** 站点与品牌身份。 */
export interface Identity {
  site: Record<string, unknown>;
  brand: Record<string, unknown>;
}
