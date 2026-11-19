/**
 * 活动数据的读取。
 *
 * 数据来自 `site/data/activity.compiled.json`——那是
 * `site/tools/build-activity.py` 编译出来的：账本（`data/activity.json`）
 * + 内容单元 → 逐日记录（每天写了什么、算不算学习、算不算用了 AI）。
 *
 * **站点不自己算**：口径写在账本的 `rules` 里，编译那边有闸门，
 * 页面这边只负责把数字与时间轴摆出来。
 *
 * 数据只来自两条：站点的账本，和 `docs/` 编译出来的内容单元。
 * 站点不去挖仓库的旧历史——**往后的账自己攒**。
 */
import activity from '../../data/activity.compiled.json';

export interface ActivityDoc {
  id: string;
  title: string;
  kind: string;
  line: string;
  url: string;
}

export interface ActivityDay {
  date: string;
  write: boolean;
  learn: boolean;
  ai: boolean;
  /** 当天写出来的东西有几篇 */
  n: number;
  note: string;
  docs: ActivityDoc[];
}

export interface ActivityStat {
  label: string;
  /** 末尾连着的天数 */
  streak: number;
  /** 累计天数 */
  total: number;
  /** 最后一次活跃的日子 */
  last: string | null;
}

export type ActivityKey = 'write' | 'learn' | 'ai' | 'slack';

interface ActivityData {
  generated: string;
  range: { start: string; end: string; days: number };
  stats: Record<ActivityKey, ActivityStat>;
  since_output: number | null;
  learn_lines: string[];
  days: ActivityDay[];
}

const data = activity as unknown as ActivityData;

export const range = data.range;
export const stats = data.stats;
export const sinceOutput = data.since_output;
export const learnLines = data.learn_lines;
export const days = data.days;

/** 有动静的日子：有产出，或者账本里记了用了 AI。 */
export function isActive(day: ActivityDay): boolean {
  return day.write || day.ai;
}

export interface ActivityMonth {
  /** "2026-11" */
  key: string;
  /** "2026 年 11 月" */
  label: string;
  days: ActivityDay[];
  /** 这个月写了几天 */
  wrote: number;
  /** 这个月写了多少篇 */
  docs: number;
  /** 这个月停了几天（既没产出、账本里也没记） */
  slack: number;
}

function monthLabel(key: string): string {
  const [y, m] = key.split('-');
  return `${y} 年 ${Number(m)} 月`;
}

/** 按月分组。新的月份在前。 */
export function months(): ActivityMonth[] {
  const groups = new Map<string, ActivityMonth>();
  for (const day of days) {
    const key = day.date.slice(0, 7);
    let group = groups.get(key);
    if (!group) {
      group = { key, label: monthLabel(key), days: [], wrote: 0, docs: 0, slack: 0 };
      groups.set(key, group);
    }
    group.days.push(day);
    if (day.write) group.wrote += 1;
    if (!day.write && !day.ai) group.slack += 1;
    group.docs += day.n;
  }
  return [...groups.values()].reverse();
}

/** 「2026-11-18」→「11-18」 */
export function shortDate(date: string): string {
  return date.slice(5);
}
