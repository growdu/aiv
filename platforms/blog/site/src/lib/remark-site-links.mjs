/**
 * 站内链接与图片的重写。
 *
 * **为什么在渲染层做**：母稿里的链接是**相对路径**（`./postgresql基操.md`），
 * 那是仓库里的写法。站点的 URL 是另一套（文档前缀 + 内容单元的目录链）。
 * 这层翻译必须做，但：
 *
 * - **不许用正则改原文**。旧站点的 `rewrite_links` / `rewrite_images` 是
 *   无视围栏的全局正则，会改到代码块里的内容——仓库里就有 5 处代码块里含
 *   markdown 链接样式的文本。这里在 **AST 上**改 `url` 字段，代码块里的
 *   东西一个都不碰。
 * - **只在渲染时改**。`content/units/` 里的内容单元保持原样，链接重写是
 *   站点这一层的事。
 *
 * **URL 形状不在这里定**：形状在仓库根的 `rules/urls.json`（全仓库唯一的那份），
 * 由 `astro.config.mjs` 把路径递进来（`rulesPath`）——插件**不自己找**规则文件，
 * 跟 `unitsBase` / `imagesBase` 一个路子。
 */
import fs from 'node:fs';
import path from 'node:path';

const EXTERNAL = /^(https?:|mailto:|tel:|data:|#|\/\/)/;
const IMAGE_EXT = /\.(png|jpe?g|gif|svg|webp|avif)$/i;

/** 规则里必须有的键。少一个就是规则文件坏了。 */
const REQUIRED_RULE_KEYS = [
  'doc_prefix',
  'video_prefix',
  'video_id_prefix',
  'category_suffix',
  'trailing_slash',
];

/**
 * 旧站点的视频地址形如 `/2026/11/12/video/row-lock/`（日期 + video/ + slug）。
 * 视频单元的口播稿里互相引用时用的就是这种写法——它们在旧站点上是活的，
 * 换到新站点必须跟着换，不然一串死链。
 *
 * 这里只认一种形状：`<年>/<月>/<日>/video/<slug>`。slug 也就是内容单元的
 * 文件名，与视频前缀下的 `<slug>/` 一一对应。
 */
const OLD_VIDEO_URL = /^\/\d{4}\/\d{2}\/\d{2}\/video\/([^/]+)\/?$/;

function walk(node, fn) {
  fn(node);
  if (node.children) for (const child of node.children) walk(child, fn);
}

/** 读规则文件。读不到或缺键就抛——宁可不构建，也不要拼出错地址。 */
function loadRules(rulesPath) {
  let raw;
  try {
    raw = fs.readFileSync(rulesPath, 'utf8');
  } catch (err) {
    throw new Error(`remark-site-links: 读不到规则文件 ${rulesPath}（${err.message}）`);
  }
  let rules;
  try {
    rules = JSON.parse(raw);
  } catch (err) {
    throw new Error(`remark-site-links: 规则文件不是合法的 JSON ${rulesPath}（${err.message}）`);
  }
  const missing = REQUIRED_RULE_KEYS.filter((key) => !(key in rules));
  if (missing.length > 0) {
    throw new Error(`remark-site-links: 规则文件缺键 ${missing.join(', ')}（${rulesPath}）`);
  }
  return rules;
}

export default function remarkSiteLinks(options = {}) {
  const unitsBase = options.unitsBase;
  const imagesBase = options.imagesBase;
  const rulesPath = options.rulesPath;

  if (!unitsBase) {
    throw new Error('remark-site-links: 缺 unitsBase 选项');
  }
  if (!imagesBase) {
    throw new Error('remark-site-links: 缺 imagesBase 选项');
  }
  if (!rulesPath) {
    throw new Error('remark-site-links: 缺 rulesPath 选项');
  }

  const rules = loadRules(rulesPath);
  const slash = rules.trailing_slash ? '/' : '';
  // 内容单元里的视频那一支：目录名（不带尾斜杠）与带尾斜杠的前缀两种写法都认。
  const videoDir = rules.video_id_prefix.replace(/\/+$/, '');

  /** 前缀 + 尾巴；尾巴为空时就是前缀本身。 */
  const withPrefix = (prefix, tail) => (tail ? prefix + tail + slash : prefix);
  const docUrl = (tail) => withPrefix(rules.doc_prefix, tail);
  const videoUrl = (tail) => withPrefix(rules.video_prefix, tail);

  return (tree, file) => {
    const filePath = file?.path;
    if (!filePath) return;

    const unitRel = path.relative(unitsBase, filePath);
    // 内容单元的目录结构与 docs/ 同构，图片按 docs/ 的相对路径解析——
    // 基准是站点的**图片副本**（public/images/），不是 docs/。
    const unitDir = path.dirname(unitRel);
    const isVideo =
      unitRel.startsWith(videoDir + path.sep) || unitRel.startsWith(rules.video_id_prefix);

    walk(tree, (node) => {
      if (node.type !== 'link' && node.type !== 'image') return;
      const url = node.url;
      if (typeof url !== 'string' || !url || EXTERNAL.test(url)) return;

      if (node.type === 'image') {
        if (!IMAGE_EXT.test(url)) return;
        if (isVideo) return; // 视频单元的图片暂不在站内托管
        const abs = path.resolve(imagesBase, unitDir, url);
        const rel = path.relative(imagesBase, abs);
        if (rel.startsWith('..')) return;
        if (!fs.existsSync(abs)) return;
        node.url = '/images/' + rel.split(path.sep).join('/');
        return;
      }

      const oldVideo = OLD_VIDEO_URL.exec(url);
      if (oldVideo) {
        node.url = videoUrl(oldVideo[1]);
        return;
      }

      if (!url.endsWith('.md')) return;
      const abs = path.resolve(path.dirname(filePath), url);
      const rel = path.relative(unitsBase, abs);
      if (rel.startsWith('..')) return;
      if (!fs.existsSync(abs)) return; // 链接指向的东西不在站上，交给链接检查去报

      const id = rel.replace(/\.md$/, '');
      if (path.basename(id) === rules.category_suffix) {
        // 分类页：文档前缀 + 目录链
        const dir = path.dirname(id).split(path.sep).join('/');
        node.url = docUrl(dir);
      } else if (id.startsWith(rules.video_id_prefix)) {
        node.url = videoUrl(id.slice(rules.video_id_prefix.length));
      } else {
        node.url = docUrl(id.split(path.sep).join('/'));
      }
    });
  };
}
