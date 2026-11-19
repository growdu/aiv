/**
 * 删掉正文开头那个 H1。
 *
 * 母稿的开头照惯例有一个 `# 标题`，而站点页面顶部**已经**渲染了一遍
 * front matter 里的 title——两处一模一样，看起来像渲染坏了。
 *
 * 这里在 AST 上把正文第一个 H1 摘掉（只在它是正文的第一个块级节点时）。
 * 正文一个字都不改，只是别让它跟页面标题重复。
 */
export default function remarkDropFirstH1() {
  return (tree) => {
    const first = tree.children?.[0];
    if (!first) return;
    if (first.type !== 'heading' || first.depth !== 1) return;
    tree.children.shift();
  };
}
