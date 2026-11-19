/**
 * 目录树。
 *
 * **树 = docs/ 的真实目录结构，一比一。**
 *
 * 内容单元的 id 就是它相对 docs/ 的路径（不带 .md）：
 *
 *   source-tracks/postgresql/_index              → 目录节点（分类页）
 *   source-tracks/postgresql/getting-started/_index
 *   source-tracks/postgresql/getting-started/postgresql基操  → 叶子节点（文章）
 *   video/row-lock                               → 视频线的另一支
 *
 * 所以树的形状**不用另造**：把 id 切开就是树。
 * 站点不发明分类体系——《目录即接口》：一级目录就是分类，
 * 分类只存在于目录里；_index.md 是那个目录的落地页。
 *
 * 左栏显示的就是这棵树（见 `components/DocTree.astro`），
 * 当前文章所在那一支默认展开、当前文章高亮。
 *
 * 学习流（赛道 / 阶段）**折进树里**：阶段本来就是目录
 * （`source-tracks/postgresql/getting-started/` 就是 L1），
 * 所以节点上直接挂阶段标记，不再单占一栏。
 */
import type { Unit } from './units';
import { RULES, stripCategorySuffix } from './rules';
import { unitUrl } from './urls';

export interface TreeNode {
  /** 目录节点 = 目录路径；叶子节点 = 内容单元 id */
  key: string;
  /** 显示名：目录用目录名，叶子用文章标题 */
  name: string;
  kind: 'dir' | 'leaf';
  /** 有页面才链得上（没有 _index.md 的目录没有页面） */
  href?: string;
  /** 这个节点背后的内容单元 id（目录节点 = 它的 _index） */
  unitId?: string;
  /** 目录节点的分类页标题（做 title 提示用） */
  title?: string;
  children: TreeNode[];
  /** 子树里出现过的阶段 id（L1、L2……） */
  stages: string[];
  /** 在当前文章的祖先链上（决定默认展开） */
  onPath: boolean;
  /** 就是当前文章 */
  current: boolean;
}

export interface TreeRoot {
  /** docs/ 的顶层目录们 */
  docs: TreeNode[];
  /** video/ 那支（视频线的产物，不在 docs/ 里） */
  video: TreeNode | undefined;
}

function emptyNode(key: string, name: string, kind: 'dir' | 'leaf'): TreeNode {
  return {
    key,
    name,
    kind,
    children: [],
    stages: [],
    onPath: false,
    current: false,
  };
}

/**
 * 把内容单元拼成一棵树。
 *
 * @param units    全量内容单元
 * @param currentId 当前文章的内容单元 id
 */
export function buildTree(units: Unit[], currentId: string): TreeRoot {
  const dirs = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];
  const videoUnits: Unit[] = [];

  /** 拿到（或建出）某个目录节点，顺手把祖先链建出来。 */
  const ensureDir = (path: string[]): TreeNode => {
    const key = path.join('/');
    const found = dirs.get(key);
    if (found) return found;

    const node = emptyNode(key, path[path.length - 1], 'dir');
    dirs.set(key, node);

    const parent = path.length > 1 ? ensureDir(path.slice(0, -1)) : undefined;
    (parent ? parent.children : roots).push(node);
    return node;
  };

  for (const unit of units) {
    if (unit.data.kind === 'video' || unit.id.startsWith(RULES.video_id_prefix)) {
      videoUnits.push(unit);
      continue;
    }

    const segs = unit.id.split('/');
    const isIndex = segs[segs.length - 1] === RULES.category_suffix;
    const parent = segs.length > 1 ? ensureDir(segs.slice(0, -1)) : undefined;

    if (isIndex) {
      // 这个目录有落地页（_index.md）：目录节点自己链到分类页
      const dir = parent!;
      dir.unitId = unit.id;
      dir.href = unitUrl(unit.id, 'category');
      dir.title = unit.data.title;
    } else {
      const leaf = emptyNode(unit.id, unit.data.title, 'leaf');
      leaf.href = unitUrl(unit.id, unit.data.kind);
      leaf.unitId = unit.id;
      (parent ? parent.children : roots).push(leaf);
    }
  }

  // 视频那一支：根目录 video/ 链到 /videos/，下面是每一期
  let video: TreeNode | undefined;
  if (videoUnits.length > 0) {
    const root = emptyNode('video', 'video', 'dir');
    root.href = RULES.video_prefix;
    root.title = '视频';
    for (const unit of videoUnits) {
      const leaf = emptyNode(unit.id, unit.data.title, 'leaf');
      leaf.href = unitUrl(unit.id, 'video');
      leaf.unitId = unit.id;
      root.children.push(leaf);
    }
    video = root;
  }

  const tree: TreeRoot = { docs: roots, video };

  // 当前文章的位置：祖先链上的目录 onPath，当前文章 current
  markCurrent(tree, currentId);

  // 排序 + 阶段标记
  sortTree(tree);
  return tree;
}

function markCurrent(tree: TreeRoot, currentId: string): void {
  // 分类页的 id 带分类页后缀，树上它的键是目录路径本身
  const key = stripCategorySuffix(currentId);
  const current = findNode(tree, key);
  if (!current) return;
  current.current = true;
  // 当前就是目录时（分类页），把它自己也展开——不然看不到目录里有什么
  if (current.kind === 'dir') current.onPath = true;

  // 祖先链：从当前节点的 key 逐级往上
  const segs = current.key.split('/');
  let path = segs.slice(0, -1);
  while (path.length > 0) {
    const dir = findNode(tree, path.join('/'));
    if (dir) dir.onPath = true;
    path = path.slice(0, -1);
  }
}

function findNode(tree: TreeRoot, key: string): TreeNode | undefined {
  const walk = (nodes: TreeNode[]): TreeNode | undefined => {
    for (const node of nodes) {
      if (node.key === key) return node;
      const hit = walk(node.children);
      if (hit) return hit;
    }
    return undefined;
  };
  return walk(tree.docs) ?? (tree.video ? walk([tree.video]) : undefined);
}

/** 目录在前、文档在后，各自按中文名排序（跟文件管理器一个脾气）。 */
function sortTree(tree: TreeRoot): void {
  const byName = (a: TreeNode, b: TreeNode) => a.name.localeCompare(b.name, 'zh');
  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'dir' ? -1 : 1;
      return byName(a, b);
    });
    for (const node of nodes) sortNodes(node.children);
  };
  sortNodes(tree.docs);
  if (tree.video) sortNodes(tree.video.children);
}

/**
 * 把学习流的阶段折进树里。
 *
 * 阶段本来就是目录（`…/getting-started/` 就是 L1），
 * 所以标记挂在节点上：叶子挂自己的阶段；目录**只有在直接装着同一个阶段的文章时**
 * 才挂（`getting-started/` 下面都是 L1 的文章 → 标 L1；
 * `postgresql/` 下面装的是阶段目录 → 不标，标谁都假）。
 *
 * @param stageOf 内容单元 id → 阶段 id（L1、L2……），没归类返回 undefined
 */
export function attachStages(tree: TreeRoot, stageOf: (unitId: string) => string | undefined): void {
  const visit = (node: TreeNode): string[] => {
    if (node.kind === 'leaf') {
      const own = node.unitId ? stageOf(node.unitId) : undefined;
      node.stages = own ? [own] : [];
      return node.stages;
    }
    // 目录：只看直接挂在底下的**文章**，不看子目录
    const leafStages = node.children
      .filter((child) => child.kind === 'leaf')
      .flatMap((child) => visit(child));
    node.stages = [...new Set(leafStages)];
    // 子目录自己递归（它们的标记算在它们自己头上）
    for (const child of node.children) {
      if (child.kind === 'dir') visit(child);
    }
    return node.stages;
  };
  for (const node of tree.docs) visit(node);
  if (tree.video) visit(tree.video);
}

