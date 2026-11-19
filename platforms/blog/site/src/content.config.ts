import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

/**
 * 内容单元集合。
 *
 * 一个集合装两类东西：文档（docs/ 编出来的）与视频（video/ 编出来的）。
 * 站点不区分它们是「文章」还是「视频」——学习流把两者放在同一张阶梯上，
 * 靠 `kind` 区分渲染方式就够了。
 *
 * 副本是 `tools/sync-content.py` 从 `content/units/` 同步过来的构建产物。
 */
const units = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/units' }),
  schema: z.object({
    title: z.string(),
    date: z.union([z.string(), z.date()]),
    author: z.string().optional(),
    description: z.string().optional(),
    kind: z.enum(['document', 'category', 'video']).default('document'),
    categories: z.array(z.string()).default([]),
    tags: z.array(z.string()).default([]),
    source_path: z.string().optional(),
    /** 视频单元：发到了哪些平台 */
    platforms: z.array(z.string()).optional(),
  }),
});

/**
 * 站点自己的页面（不是内容单元）。
 *
 * 跟内容单元分开，是因为**来路不同**：内容单元是 `docs/` 编出来的，
 * 过审才上站；这些页面是站点这一层的私产，由使用者自己写
 * （现在只有「关于」页，`content/about.md`）。
 *
 * 目录 `content/` 在工程根下，不在 `src/` 里——它不是构建产物，
 * 是使用者改得动的东西。
 */
const pages = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './content' }),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
  }),
});

export const collections = { units, pages };
