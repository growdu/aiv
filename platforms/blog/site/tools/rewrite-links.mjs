#!/usr/bin/env node
/**
 * 正文里的相对链接 → 站上的地址。
 *
 * **为什么在渲染前做**：母稿里的链接是**相对路径**（`../某篇.md`），
 * 那是仓库里的写法。站点的 URL 是另一套（文档前缀 + 单元 id）。
 * 这层翻译必须做，但：
 *
 * - **不许用正则改原文**。无视围栏的全局正则会改到代码块里的内容——
 *   仓库里就有代码块里含 markdown 链接样式的文本。这里在 **AST 上**定位
 *   节点（remark 解析），再按节点位置**外科式**替换原文的那一小段，
 *   其余一个字都不动，代码块里的东西一个都不碰。
 * - **形状只有一处说了算**：`source/_data/urls.json`（由
 *   `tools/build-posts.py` 从 `tools/urls.py` 写出来）。
 *
 * **改了哪几样**：
 *
 * 1. 相对 markdown 链接（`../某篇.md`）→ 站上那篇的地址；
 * 2. 旧站点的视频地址（`/2026/11/12/video/row-lock/`）→ 新站的视频地址；
 * 3. 相对图片（`./图.png`）→ `/images/<相对路径>`；
 * 4. 正文开头那个 H1 —— 页面顶部已经渲染过 front matter 里的 title 了，
 *    两处一模一样看着像渲染坏了。
 *
 * **跑几遍都是同一个结果**（幂等）：改完的地址是绝对的（以文档前缀开头），
 * 下一次直接跳过；开头的 H1 摘掉之后就没有了。
 *
 * 用法：
 *
 *     node platforms/blog/site/tools/rewrite-links.mjs
 *     node platforms/blog/site/tools/rewrite-links.mjs --check
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { unified } from 'unified';
import remarkParse from 'remark-parse';

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const POSTS_DIR = path.join(SITE, 'source', '_posts');
const DATA_DIR = path.join(SITE, 'source', '_data');
const IMAGES_DIR = path.join(SITE, 'source', 'images');
const URLS_FILE = path.join(DATA_DIR, 'urls.json');

/** 已经是绝对地址的（外部链接、站内绝对路径、锚点）——不碰。 */
const ABSOLUTE = /^(?:[a-z][a-z0-9+.-]*:|\/\/|\/|#)/i;

/**
 * 拆出 front matter 与正文。
 *
 * **为什么要在解析之前拆**：markdown 解析器不认识 hexo 的 front matter——
 * 开头的 `---` 在它眼里是一条**分隔线**。不拆的话，正文的第一个块级节点
 * 就不是那个 H1，「摘掉开头标题」这件事也就做不成。
 *
 * 返回 {head, body}。没有 front matter 时 head 是空串。
 */
function splitFrontMatter(text) {
  if (!text.startsWith('---')) return { head: '', body: text };
  const end = text.indexOf('\n---', 3);
  if (end === -1) return { head: '', body: text };
  const after = text.slice(end + 4);
  const close = after.indexOf('\n');
  if (close === -1) return { head: '', body: text };
  // 结尾的 `---` 之后应当是空行或正文。
  const head = text.slice(0, end + 4 + close + 1);
  return { head, body: after.slice(close + 1) };
}

/** 图片后缀。正文里的图片指向这些后缀的文件时才做重写。 */
const IMAGE_SUFFIX = /\.(?:png|jpe?g|gif|svg|webp|avif)$/i;

/** 旧站点的视频地址：`<年>/<月>/<日>/video/<slug>`。 */
const OLD_VIDEO_URL = /^\/\d{4}\/\/\d{2}\/\/\d{2}\/video\/([^/]+)\/?$/;

const processor = unified().use(remarkParse);

/**
 * 解码 URL 里的百分号编码。解不开就原样返回（不因为一个坏编码崩掉整轮）。
 */
function safeDecode(text) {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

/** 把链接拆成「路径」与「尾巴」（查询串 + 锚点）。 */
function splitTail(url) {
  const match = /^([^?#]*)([?#].*)?$/.exec(url);
  return {
    path: match ? match[1] : url,
    tail: match && match[2] ? match[2] : '',
  };
}

/** 走一遍 AST，收集所有要改的节点。 */
function collect(tree) {
  const links = [];
  const images = [];

  const walk = (node) => {
    if (node.type === 'link') links.push(node);
    else if (node.type === 'image') images.push(node);
    if (node.children) for (const child of node.children) walk(child);
  };

  walk(tree);
  return { links, images };
}

/**
 * 从 `[文字](地址 "标题")` 的原文里找出地址那一段的位置。
 *
 * 返回相对**节点起点**的偏移 {start, end}；不是这种形状就返回 null
 * （参考式链接、`<尖括号>` 包裹的地址另说）。
 */
function urlSpanInInline(raw) {
  if (!raw.endsWith(')')) return null;

  // 从后往前扫，找与末尾那个 `)` 配对的 `(`。
  let depth = 0;
  for (let i = raw.length - 1; i >= 0; i -= 1) {
    const ch = raw[i];
    if (ch === ')') depth += 1;
    else if (ch === '(') {
      depth -= 1;
      if (depth === 0) {
        const inner = raw.slice(i + 1, raw.length - 1);
        const angled = /^\s*<([^>]*)>/.exec(inner);
        if (angled) {
          const start = i + 1 + inner.indexOf('<') + 1;
          return { start, end: start + angled[1].length };
        }
        const space = inner.search(/\s/);
        if (space === -1) return { start: i + 1, end: i + 1 + inner.length };
        return { start: i + 1, end: i + 1 + space };
      }
    }
  }
  return null;
}

/**
 * 相对链接 → 内容单元 id。
 *
 * `postRel` 是文章相对 `source/_posts/` 的路径（带 `.md`），
 * `linkPath` 是链接里的路径部分。返回 null 表示「指到站外去了」。
 */
function unitIdOf(postRel, linkPath) {
  const decoded = safeDecode(linkPath);
  const base = path.posix.dirname(postRel);
  const joined = path.posix.normalize(path.posix.join(base === '.' ? '' : base, decoded));
  if (joined.startsWith('..')) return null;
  const id = joined.replace(/\.md$/, '');
  return id || null;
}

/** 一篇文章重写后的样子。 */
function rewritePost(text, postRel, urls) {
  const { head, body } = splitFrontMatter(text);
  const tree = processor.parse(body);
  const { links, images } = collect(tree);

  /** 待替换的片段：{start, end, text}，偏移是相对整篇正文。 */
  const edits = [];
  const unresolved = [];

  const replaceUrl = (node, raw, next) => {
    const span = urlSpanInInline(raw);
    if (!span) {
      unresolved.push({ post: postRel, url: node.url, reason: '不是行内链接的形状' });
      return;
    }
    edits.push({
      start: node.position.start.offset + span.start,
      end: node.position.start.offset + span.end,
      text: next,
    });
  };

  for (const node of links) {
    const url = node.url;
    if (typeof url !== 'string' || !url) continue;

    const raw = body.slice(node.position.start.offset, node.position.end.offset);
    const { path: linkPath, tail } = splitTail(url);

    // 旧站点的视频地址：日期前缀那一套（它也是绝对路径，得先认出来）。
    const oldVideo = OLD_VIDEO_URL.exec(url);
    if (oldVideo) {
      const target = urls[`video/${oldVideo[1]}`];
      if (target) {
        replaceUrl(node, raw, target + tail);
        continue;
      }
    }

    // 站内绝对地址和外链都不碰。
    if (ABSOLUTE.test(url)) continue;

    if (!linkPath.endsWith('.md')) continue;
    const id = unitIdOf(postRel, linkPath);
    if (!id) continue;
    const target = urls[id];
    if (!target) {
      unresolved.push({ post: postRel, url, reason: `地址表里没有 ${id}` });
      continue;
    }
    replaceUrl(node, raw, target + tail);
  }

  for (const node of images) {
    const url = node.url;
    if (typeof url !== 'string' || !url || ABSOLUTE.test(url)) continue;
    if (!IMAGE_SUFFIX.test(url)) continue;

    const { path: linkPath } = splitTail(url);
    const id = unitIdOf(postRel, linkPath);
    if (!id) continue;

    const rel = id.split(path.posix.sep).join('/');
    if (!fs.existsSync(path.join(IMAGES_DIR, rel))) {
      unresolved.push({ post: postRel, url, reason: `图片没搬过来：images/${rel}` });
      continue;
    }

    const raw = body.slice(node.position.start.offset, node.position.end.offset);
    replaceUrl(node, raw, `/images/${rel}`);
  }

  // 正文开头那个 H1：页面顶部已经渲染过标题了。
  const first = tree.children && tree.children[0];
  if (first && first.type === 'heading' && first.depth === 1) {
    edits.push({
      start: first.position.start.offset,
      end: first.position.end.offset,
      text: '',
    });
  }

  if (edits.length === 0) return { text, changed: false, unresolved };

  // 从后往前替换，前面的偏移才不受影响。
  edits.sort((a, b) => b.start - a.start);
  let out = body;
  for (const edit of edits) {
    out = out.slice(0, edit.start) + edit.text + out.slice(edit.end);
  }
  // 摘掉开头的标题之后，正文前面会空出一串空行——收成一行。
  out = out.replace(/^\n+/, '\n');
  return { text: head + out, changed: true, unresolved };
}

/** 站点里所有文章（相对 `source/_posts/` 的路径）。 */
function postFiles() {
  if (!fs.existsSync(POSTS_DIR)) return [];
  const out = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.md')) out.push(full);
    }
  };
  walk(POSTS_DIR);
  return out.sort();
}

function main() {
  const check = process.argv.includes('--check');

  if (!fs.existsSync(URLS_FILE)) {
    console.error(`地址表不存在：${URLS_FILE}\n（先跑 python3 tools/build-posts.py）`);
    return 2;
  }
  const urls = JSON.parse(fs.readFileSync(URLS_FILE, 'utf8'));

  const files = postFiles();
  let changedCount = 0;
  const unresolved = [];

  for (const file of files) {
    const postRel = path.relative(POSTS_DIR, file).split(path.sep).join('/');
    const original = fs.readFileSync(file, 'utf8');
    const { text, changed, unresolved: misses } = rewritePost(original, postRel, urls);
    unresolved.push(...misses);
    if (!changed) continue;
    changedCount += 1;
    if (check) {
      console.error(`${postRel}：还没重写`);
    } else {
      fs.writeFileSync(file, text, 'utf8');
    }
  }

  if (check) {
    if (changedCount > 0) {
      console.error(`\n${changedCount} 篇文章还没重写（跑一次 rewrite-links.mjs）`);
      return 1;
    }
    console.log(`链接已重写（${files.length} 篇）`);
    return 0;
  }

  if (unresolved.length > 0) {
    console.log(`没能翻译的链接 ${unresolved.length} 处（留着原样，交给链接检查去报）：`);
    for (const item of unresolved) {
      console.log(`  ${item.post}：${item.url} —— ${item.reason}`);
    }
  }
  console.log(`链接重写：${files.length} 篇文章，改了 ${changedCount} 篇`);
  return 0;
}

process.exit(main());
