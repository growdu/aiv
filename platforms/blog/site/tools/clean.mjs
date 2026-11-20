#!/usr/bin/env node
/**
 * 清掉上一次的构建产物。
 *
 * **为什么不用 `hexo clean`**：它会把产物目录整个删掉再重建。某些文件系统
 * （网络盘、FUSE 挂载）上，目录里可能有「已删除但仍被打开」的文件——
 * 那种文件删不掉，目录也就永远删不掉，`hexo clean` 于是报 ENOTEMPTY。
 *
 * 这里改成**清空目录的内容**，目录本身留着。删不掉的那些文件就留着
 * （它们是上一次构建的残留，不影响这一次）。
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIST = path.join(SITE, 'dist');
const CACHE = path.join(SITE, 'db.json');

async function empty(dir) {
  let entries;
  try {
    entries = await fs.readdir(dir);
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
  const leftovers = [];
  for (const entry of entries) {
    const full = path.join(dir, entry);
    try {
      await fs.rm(full, { recursive: true, force: true });
    } catch {
      leftovers.push(entry);
    }
  }
  return leftovers;
}

async function main() {
  const leftovers = await empty(DIST);
  await fs.rm(CACHE, { force: true }).catch(() => {});

  if (leftovers.length > 0) {
    console.log(`产物目录里这几个文件删不掉（不影响本次构建）：${leftovers.join('、')}`);
  }
  console.log('产物已清空');
}

await main();
