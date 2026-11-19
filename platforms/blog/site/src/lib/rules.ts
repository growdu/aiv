/**
 * 共享 URL 规则（站点这一侧的读取器）。
 *
 * **规则只有一份**：仓库根的 `rules/urls.json`。形状在那边定，
 * 这边只负责读——站点里**没有任何一处**再写死文档前缀或视频前缀。
 *
 * **为什么用 JSON import 而不是 `readFileSync`**：JSON import 由 Vite 在
 * 构建时直接内联进产物，不碰文件系统。`readFileSync` + `import.meta.url`
 * 在打包后会指向**产物目录**，规则就找不到了。
 *
 * ⚠️ 相对路径是**五级**：`src` → `site` → `blog` → `platforms` → 仓库根。
 */
import raw from '../../../../../rules/urls.json';

export const RULES = raw as {
  version: number;
  doc_prefix: string;
  video_prefix: string;
  video_id_prefix: string;
  category_suffix: string;
  trailing_slash: boolean;
};
