/**
 * 把 ```mermaid 代码块变成 `<div class="mermaid">`，交给客户端的 mermaid 渲染。
 *
 * **为什么在客户端渲染**（理由见 design 文档 §七）：
 *
 * - 构建期渲染需要 chromium（mermaid-cli）或 jsdom（部分图型会挂），
 *   CI 要多背几百 MB，构建也慢；
 * - 流程图分散在几百个页面里，**单页通常只有一两张**，客户端负担被分摊掉了；
 * - mermaid 源码留在 HTML 里，搜索引擎读得到。
 *
 * 失败的图不阻断页面：mermaid 渲染出错时 div 里留着源码，页面上就是一段文本。
 */

function textOf(node) {
  if (typeof node.value === 'string') return node.value;
  if (!node.children) return '';
  return node.children.map(textOf).join('');
}

function walk(node, fn) {
  fn(node);
  if (node.children) for (const child of node.children) walk(child, fn);
}

export default function rehypeMermaid() {
  return (tree) => {
    walk(tree, (node) => {
      if (node.type !== 'element' || node.tagName !== 'pre') return;
      const code = node.children?.[0];
      if (!code || code.tagName !== 'code') return;
      const classes = code.properties?.className || [];
      const list = Array.isArray(classes) ? classes : String(classes).split(/\s+/);
      if (!list.includes('language-mermaid')) return;

      const source = textOf(code);
      node.tagName = 'div';
      node.properties = { className: ['mermaid'] };
      node.children = [{ type: 'text', value: source }];
    });
  };
}
