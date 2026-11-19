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

export const collections = { units };
