/**
 * URL 规则。站点里**只有这一处**决定链接长什么样。
 *
 * 形状本身不在这里——它在仓库根的 `rules/urls.json`（全仓库唯一的那份），
 * 这里只负责读（`./rules.ts`）并把它套到单元 id 上。
 *
 * 单元 id 是内容单元相对 `content/units/` 的路径（不带 .md）：
 *   source-tracks/postgresql/getting-started/postgresql基操
 *   source-tracks/postgresql/_index        ← 分类页
 *   video/row-lock                          ← 视频
 *
 * 文档与分类页走文档前缀，视频走视频前缀——前缀由规则给。
 *
 * ⚠️ 分类页的 id 尾巴带分类页后缀、视频的 id 开头带视频前缀——
 * 那是**内容单元里的形状**，不是 URL 里的形状。这里负责把这两处形状抹掉。
 * 漏抹一次就是一批死链（`site/tests/test_pages.py` 守着这件事）。
 */
import { RULES } from './rules';

function stripVideoPrefix(id: string): string {
  const prefix = RULES.video_id_prefix;
  return prefix && id.startsWith(prefix) ? id.slice(prefix.length) : id;
}

function stripCategorySuffix(id: string): string {
  const suffix = RULES.category_suffix;
  const tail = suffix ? '/' + suffix : '';
  return tail && id.endsWith(tail) ? id.slice(0, -tail.length) : id;
}

/** 前缀 + 单元 id 的尾巴；尾巴为空时就是前缀本身。 */
function join(prefix: string, tail: string): string {
  if (!tail) return prefix;
  return prefix + tail + (RULES.trailing_slash ? '/' : '');
}

export function unitUrl(id: string, kind: string): string {
  if (kind === 'video') return videoUrl(id);
  return docUrl(id);
}

export function docUrl(id: string): string {
  return join(RULES.doc_prefix, stripCategorySuffix(id));
}

export function videoUrl(id: string): string {
  return join(RULES.video_prefix, stripVideoPrefix(id));
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
