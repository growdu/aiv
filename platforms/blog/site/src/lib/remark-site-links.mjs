/**
 * 站内链接与图片的重写。
 *
 * **为什么在渲染层做**：母稿里的链接是**相对路径**（`./postgresql基操.md`），
 * 那是仓库里的写法。站点的 URL 是另一套（`/docs/source-tracks/postgresql/...`）。
 * 这层翻译必须做，但：
 *
 * - **不许用正则改原文**。旧站点的 `rewrite_links` / `rewrite_images` 是
 *   无视围栏的全局正则，会改到代码块里的内容——仓库里就有 5 处代码块里含
 *   markdown 链接样式的文本。这里在 **AST 上**改 `url` 字段，代码块里的
 *   东西一个都不碰。
 * - **只在渲染时改**。`content/units/` 里的内容单元保持原样，链接重写是
 *   站点这一层的事。
 */
import fs from 'node:fs';
import path from 'node:path';

const EXTERNAL = /^(https?:|mailto:|tel:|data:|#|\/\/)/;
const IMAGE_EXT = /\.(png|jpe?g|gif|svg|webp|avif)$/i;

/**
 * 旧站点的视频地址形如 `/2026/11/12/video/row-lock/`（日期 + video/ + slug）。
 * 视频单元的口播稿里互相引用时用的就是这种写法——它们在旧站点上是活的，
 * 换到新站点必须跟着换，不然一串死链。
 *
 * 这里只认一种形状：`<年>/<月>/<日>/video/<slug>`。slug 也就是内容单元的
 * 文件名，与 `/videos/<slug>/` 一一对应。
 */
const OLD_VIDEO_URL = /^\/\d{4}\/\d{2}\/\d{2}\/video\/([^/]+)\/?$/;

function walk(node, fn) {
  fn(node);
  if (node.children) for (const child of node.children) walk(child, fn);
}

export default function remarkSiteLinks(options = {}) {
  const unitsBase = options.unitsBase;
  const docsBase = options.docsBase;

  if (!unitsBase) {
    throw new Error('remark-site-links: 缺 unitsBase 选项');
  }

  return (tree, file) => {
    const filePath = file?.path;
    if (!filePath) return;

    const unitRel = path.relative(unitsBase, filePath);
    // 内容单元的目录结构与 docs/ 同构，图片按 docs/ 的相对路径解析。
    const unitDir = path.dirname(unitRel);
    const isVideo = unitRel.startsWith('video' + path.sep) || unitRel.startsWith('video/');

    walk(tree, (node) => {
      if (node.type !== 'link' && node.type !== 'image') return;
      const url = node.url;
      if (typeof url !== 'string' || !url || EXTERNAL.test(url)) return;

      if (node.type === 'image') {
        if (!IMAGE_EXT.test(url)) return;
        if (isVideo) return; // 视频单元的图片暂不在站内托管
        const abs = path.resolve(docsBase, unitDir, url);
        const rel = path.relative(docsBase, abs);
        if (rel.startsWith('..')) return;
        if (!fs.existsSync(abs)) return;
        node.url = '/images/' + rel.split(path.sep).join('/');
        return;
      }

      const oldVideo = OLD_VIDEO_URL.exec(url);
      if (oldVideo) {
        node.url = `/videos/${oldVideo[1]}/`;
        return;
      }

      if (!url.endsWith('.md')) return;
      const abs = path.resolve(path.dirname(filePath), url);
      const rel = path.relative(unitsBase, abs);
      if (rel.startsWith('..')) return;
      if (!fs.existsSync(abs)) return; // 链接指向的东西不在站上，交给链接检查去报

      const id = rel.replace(/\.md$/, '');
      if (path.basename(id) === '_index') {
        // 分类页：/docs/<目录>/
        const dir = path.dirname(id).split(path.sep).join('/');
        node.url = dir ? `/docs/${dir}/` : '/docs/';
      } else if (id.startsWith('video/')) {
        node.url = `/videos/${id.slice('video/'.length)}/`;
      } else {
        node.url = `/docs/${id.split(path.sep).join('/')}/`;
      }
    });
  };
}
