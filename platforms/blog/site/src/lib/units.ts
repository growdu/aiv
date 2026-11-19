/**
 * 内容单元的读取。
 *
 * 单元 id 就是它相对 `content/units/` 的路径（不带 .md）：
 *   source-tracks/postgresql/getting-started/postgresql基操
 *   video/row-lock
 *   source-tracks/postgresql/_index        ← 分类页
 *
 * 这个 id 是**站点与编译器之间唯一约定的键**：编译器（build-learning-path.py）
 * 把「哪个单元属于哪条赛道哪个阶段」写进 learning-path.compiled.json，
 * 页面这边拿 id 去查，两边对不上就是构建期的问题，不是页面的问题。
 */
import { getCollection, type CollectionEntry } from 'astro:content';
import { isCategoryId as isCategoryIdByRule, stripCategorySuffix } from './rules';

export type Unit = CollectionEntry<'units'>;

export async function allUnits(): Promise<Unit[]> {
  const units = await getCollection('units');
  return sortUnits(units);
}

export function sortUnits(units: Unit[]): Unit[] {
  return [...units].sort((a, b) => {
    const ta = timeOf(a);
    const tb = timeOf(b);
    if (ta !== tb) return tb - ta;
    return a.id.localeCompare(b.id, 'zh');
  });
}

export function timeOf(unit: Unit): number {
  const raw = unit.data.date;
  const t = typeof raw === 'string' ? Date.parse(raw.replace(' ', 'T')) : raw.getTime();
  return Number.isNaN(t) ? 0 : t;
}

/** 分类页的 id 以分类页后缀结尾；文档与视频不会。
 *
 * 「后缀是什么」在共享规则里（`./rules.ts`）——这里不写死。 */
export function isCategoryId(id: string): boolean {
  return isCategoryIdByRule(id);
}

/** 分类页的 id → 目录路径（`source-tracks/postgresql/_index` → `source-tracks/postgresql`）。 */
export function categoryPath(id: string): string {
  return stripCategorySuffix(id);
}

export function unitTitle(unit: Unit): string {
  return unit.data.title;
}

export function isVideo(unit: Unit): boolean {
  return unit.data.kind === 'video';
}
