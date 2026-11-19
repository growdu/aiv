/**
 * 占位内容。
 *
 * **站点的诚实义务**：挂在站上的东西，有一篇算一篇吗？
 * 现在这六期视频是**占位稿**——口径与术语都是历史产物（「第三方开发者口径」、
 * 「沿用 EP01~EP05」那一套），跟现行的人格与术语表对不上，正在重写。
 *
 * 所以站点在页面上明说「这是占位」，不装作它们是成品。
 *
 * **这里只标状态，不改内容**：改稿是视频线的事（稿子住在 `video/`），
 * 站点这边只负责不误导读者。
 *
 * 名单在 `site/data/placeholder-units.json`；重写完删掉那个文件，
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
