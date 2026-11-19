/**
 * 共享 URL 规则（站点这一侧的读取器）。
 *
 * **规则只有一份**：仓库根的 `rules/urls.json`。形状在那边定，
 * 这边只负责读——站点里**没有任何一处**再写死文档前缀、视频前缀，
 * 连「这是不是分类页 / 这是不是视频」那两个 id 形状也不写死。
 *
 * **为什么用 JSON import 而不是 `readFileSync`**：JSON import 由 Vite 在
 * 构建时直接内联进产物，不碰文件系统。`readFileSync` + `import.meta.url`
 * 在打包后会指向**产物目录**，规则就找不到了。
 *
 * ⚠️ 相对路径是**五级**：`src` → `site` → `blog` → `platforms` → 仓库根。
 */
import raw from '../../../../../rules/urls.json';

/** 规则里必须有的键。少一个就是规则文件坏了。 */
const REQUIRED_KEYS = [
  'version',
  'doc_prefix',
  'video_prefix',
  'video_id_prefix',
  'category_suffix',
  'trailing_slash',
] as const;

const values = raw as Record<string, unknown>;

/**
 * **运行时校验**：类型断言骗不了人——键名写错只会拼出 `undefined...` 的地址，
 * 到链接检查才报，很难看出是规则读错了。这里响亮地炸。
 * （同一份规则的 JS 读取器 `remark-site-links.mjs` 也是「缺键就抛」。）
 */
const missing = REQUIRED_KEYS.filter((key) => values[key] === undefined);
if (missing.length > 0) {
  throw new Error(`rules/urls.json 缺键：${missing.join(', ')}`);
}

export const RULES = values as {
  version: number;
  doc_prefix: string;
  video_prefix: string;
  video_id_prefix: string;
  category_suffix: string;
  trailing_slash: boolean;
};

/**
 * 去掉单元 id 开头的视频前缀（`video/`）。
 *
 * 全站只有这一处做这件事——`urls.ts` / `units.ts` / `tree.ts` /
 * `videos/[ep].astro` 都用它，不许再写死 `'video/'`。
 */
export function stripVideoPrefix(id: string): string {
  const prefix = RULES.video_id_prefix;
  return prefix && id.startsWith(prefix) ? id.slice(prefix.length) : id;
}

/**
 * 去掉单元 id 结尾的分类页后缀（`/_index`）。
 *
 * 全站只有这一处做这件事——`urls.ts` / `units.ts` / `tree.ts` 都用它，
 * 不许再写死 `'_index'`。
 */
export function stripCategorySuffix(id: string): string {
  const suffix = RULES.category_suffix;
  const tail = suffix ? '/' + suffix : '';
  return tail && id.endsWith(tail) ? id.slice(0, -tail.length) : id;
}

/** 这个 id 是不是分类页（id 尾巴带分类页后缀，或它本身就是那个后缀）。 */
export function isCategoryId(id: string): boolean {
  const suffix = RULES.category_suffix;
  if (!suffix) return false;
  return id.endsWith('/' + suffix) || id === suffix;
}
