/**
 * 学习流的读取与拼接。
 *
 * 数据来自 `site/data/learning-path.compiled.json`——那是
 * `site/tools/build-learning-path.py` 编译出来的：规则表 + 内容单元 → 赛道 × 阶段。
 *
 * **站点不自己算归属**，只读编译结果。算归属是编译器的事（那边有闸门：
 * 漏归类直接构建失败），页面这边只负责把内容摆出来。
 */
import learningData from '../../data/learning-path.compiled.json';

export interface Stage {
  id: string;
  title: string;
  goal: string;
  units: string[];
  count: number;
}

export interface Track {
  id: string;
  title: string;
  summary: string;
  audience: string;
  goal: string;
  fallback_stage: string | null;
  stages: Stage[];
  count: number;
}

export interface Assignment {
  track: string;
  stage: string;
  fallback?: boolean;
}

const data = learningData as unknown as {
  generated: string;
  tracks: Track[];
  assignment: Record<string, Assignment>;
};

export const generated = data.generated;
export const tracks: Track[] = data.tracks;

export function getTrack(trackId: string): Track | undefined {
  return tracks.find((t) => t.id === trackId);
}

export function getStage(trackId: string, stageId: string): Stage | undefined {
  return getTrack(trackId)?.stages.find((s) => s.id === stageId);
}

/** 这个内容单元在哪条赛道、哪个阶段。没归类就返回 undefined。 */
export function assignmentOf(unitId: string): Assignment | undefined {
  return data.assignment[unitId];
}

/** 有内容的赛道（首页主网格用）。空赛道归到「规划中」。 */
export function tracksWithContent(): Track[] {
  return tracks.filter((t) => t.count > 0);
}

export function emptyTracks(): Track[] {
  return tracks.filter((t) => t.count === 0);
}
