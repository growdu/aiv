/* global hexo */
'use strict';

/**
 * ```mermaid 代码块 → 页面上的 <div class="mermaid">。
 *
 * **为什么要两道**：hexo 核心有个 `backtick_code_block` 过滤器，它在
 * `before_post_render` 阶段把围栏里的代码**先高亮成 HTML**（站点配置了
 * `syntax_highlighter: prismjs`）。于是围栏在 markdown 渲染之前就已经不是
 * 围栏了——到 markdown 渲染器手里的是一段 `<pre><code class="language-mermaid">`。
 *
 * 所以：
 *
 * 1. `before_post_render`：把还在的 ```mermaid 围栏换成 div
 *    （关掉服务端高亮时走这条路）；
 * 2. `after_post_render`：把剩下的 `<pre><code class="language-mermaid">`
 *    换成 div（开着服务端高亮时走这条路）。
 *
 * 两道都在，是因为**高亮这件事由配置决定**，而围栏最终要变成什么不该由
 * 配置决定。
 *
 * **内容为什么要转义**：div 里塞的是原始 HTML，mermaid 读的是它的
 * textContent。所以实体留着是对的——浏览器会把它还原成字符，正是 mermaid
 * 想要的。
 */
hexo.extend.filter.register('before_post_render', function (data) {
  data.content = data.content.replace(
    /```mermaid[ \t]*\r?\n([\s\S]*?)```/g,
    function (match, code) {
      const escaped = code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      return '<div class="mermaid">' + escaped + '</div>';
    }
  );
  return data;
});

hexo.extend.filter.register('after_post_render', function (data) {
  data.content = data.content.replace(
    /<pre[^>]*>\s*<code[^>]*class="[^"]*language-mermaid[^"]*"[^>]*>([\s\S]*?)<\/code>\s*<\/pre>/g,
    function (match, code) {
      return '<div class="mermaid">' + code + '</div>';
    }
  );
  return data;
});
