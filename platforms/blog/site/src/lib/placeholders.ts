/**
 * 占位内容。
 *
 * **站点的诚实义务**：挂在站上的东西，有一篇算一篇吗？
 * 有些内容是**占位稿**——口径与术语还在改，稿子本身先占个位。
 *
 * 所以站点在页面上明说「这是占位」，不装作它们是成品。
 *
 * **这里只标状态，不改内容**：改稿是内容线的事，站点这边只负责不误导读者。
 *
 * 名单在 `site/data/placeholder-units.json`；重写完把名单清空，
 * 站点自动恢复原样。
 */
import data from '../../data/placeholder-units.json';

const ids = new Set<string>(data.units);

export const placeholderNote: string = data.note;

/** 这个内容单元是不是占位稿。 */
export function isPlaceholder(unitId: string): boolean {
  return ids.has(unitId);
}

/** 占位的内容单元（按名单顺序）。 */
export function placeholders(): string[] {
  return [...data.units];
}
