// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { unified } from '@astrojs/markdown-remark';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import remarkSiteLinks from './src/lib/remark-site-links.mjs';
import remarkDropFirstH1 from './src/lib/remark-drop-first-h1.mjs';
import rehypeMermaid from './src/lib/rehype-mermaid.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));

/**
 * 围栏语言别名表。
 *
 * 内容里的语言标注有 40 多种，其中一批是脏的（`C`、`text`、`cmd`、`conf`、
 * `mermaind`、`dockfile`……）。Shiki 认不出的语言会静默退化成纯文本，
 * 于是这里给它们一张归一化的表——**渲染层兜住，规范问题交给围栏体检去报**。
 *
 * 表本身在 `data/lang-alias.json`（人工维护）。
 */
function loadLangAlias() {
  const file = path.join(here, 'data', 'lang-alias.json');
  const fallback = {
    C: 'c',
    'C#': 'csharp',
    text: 'plaintext',
    plaintext: 'plaintext',
    cmd: 'batch',
    bat: 'batch',
    conf: 'ini',
    cfg: 'ini',
    dockfile: 'dockerfile',
    dockerfile: 'dockerfile',
    mermaind: 'mermaid',
    mermaid: 'mermaid',
    sh: 'bash',
    shell: 'bash',
    make: 'makefile',
    makefile: 'makefile',
    md: 'markdown',
    markdown: 'markdown',
    js: 'javascript',
    javascript: 'javascript',
  };
  try {
    const raw = JSON.parse(fs.readFileSync(file, 'utf-8'));
    const table = raw.aliases ?? raw;
    return { ...fallback, ...table };
  } catch {
    return fallback;
  }
}

/**
 * Shiki 不接受「自己指向自己」的别名（`plaintext -> plaintext` 会直接报
 * Circular alias）。表里写顺手了就会踩到，所以在这里统一去掉同名的项。
 */
function withoutSelfAliases(table) {
  return Object.fromEntries(
    Object.entries(table).filter(([from, to]) => from !== to),
  );
}

// 站点地址。上线前用 SITE_URL 环境变量给正式域名；
// 本机验证用 SITE_URL=http://192.168.1.99:8080。
// 框架层不写死任何域名——那是站点自己的事。
const siteUrl = process.env.SITE_URL || 'http://localhost:4321';

// dev / preview 的主机名白名单（Astro 5.4 起）。默认只认 localhost——
// 用域名从别的机器指过来会被拒。SITE_HOSTS 是逗号分隔的额外白名单。
const extraHosts = (process.env.SITE_HOSTS || '')
  .split(',')
  .map((h) => h.trim())
  .filter(Boolean);

export default defineConfig({
  site: siteUrl,
  base: '/',
  trailingSlash: 'always',
  output: 'static',
  build: { format: 'directory' },

  integrations: [sitemap()],

  server: {
    // dev / preview 的主机名白名单（Astro 5.4 起）。
    // 默认只认 localhost——用域名从别的机器指过来会被拒。
    // （IP 访问不受这条限制，走的是 IP 那条路。）
    allowedHosts: ['localhost', ...extraHosts],
  },

  markdown: {
    // Shiki：构建期高亮，零客户端 JS。比旧站点的 Prism（运行时）快。
    // mermaid 围栏排除掉——它不是代码，交给客户端渲染（见 rehypeMermaid）。
    syntaxHighlight: { type: 'shiki', excludeLangs: ['mermaid'] },
    shikiConfig: {
      theme: 'github-light',
      wrap: false,
      langAlias: withoutSelfAliases(loadLangAlias()),
    },
    // Astro 7 默认的 markdown 处理器是 Sätteri（Rust 写的），不支持 JS 插件。
    // 我们的两层处理（链接重写、mermaid 转换）都得走 AST，所以显式换成
    // @astrojs/markdown-remark 的 unified 处理器。
    processor: unified({
      remarkPlugins: [
        remarkDropFirstH1,
        [
          remarkSiteLinks,
          {
            unitsBase: path.join(here, 'src', 'content', 'units'),
            docsBase: path.join(here, '..', '..', '..', 'docs'),
          },
        ],
      ],
      rehypePlugins: [rehypeMermaid],
    }),
  },

  vite: {
    server: { host: true },
  },
});
