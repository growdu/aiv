/**
 * URL 规则。站点里**只有这一处**决定链接长什么样。
 *
 * 单元 id 是内容单元相对 `content/units/` 的路径（不带 .md）：
 *   source-tracks/postgresql/getting-started/postgresql基操
 *   source-tracks/postgresql/_index        ← 分类页
 *   video/row-lock                          ← 视频
 *
 * 文档与分类页走 `/docs/`，视频走 `/videos/`。
 *
 * ⚠️ 分类页的 id 尾巴带 `_index`、视频的 id 开头带 `video/`——
 * 那是**内容单元里的形状**，不是 URL 里的形状。这里负责把这两处形状抹掉。
 * 漏抹一次就是一批死链（`site/tests/test_pages.py` 守着这件事）。
 */

function stripVideoPrefix(id: string): string {
  return id.replace(/^video\//, '');
}

function stripCategorySuffix(id: string): string {
  return id.replace(/\/_index$/, '');
}

export function unitUrl(id: string, kind: string): string {
  if (kind === 'video') return `/videos/${stripVideoPrefix(id)}/`;
  if (kind === 'category') return `/docs/${stripCategorySuffix(id)}/`;
  return `/docs/${id}/`;
}

export function docUrl(id: string): string {
  return `/docs/${stripCategorySuffix(id)}/`;
}

export function videoUrl(id: string): string {
  return `/videos/${stripVideoPrefix(id)}/`;
}

export function trackUrl(trackId: string): string {
  return `/learning/${trackId}/`;
}

export function stageUrl(trackId: string, stageId: string): string {
  return `/learning/${trackId}/${stageId}/`;
}

/** 单元 id → 它的「目录链」（分类链）。分类链来自母稿的 cascade。 */
export function categoryChain(categories: string[]): string[] {
  return categories;
}
