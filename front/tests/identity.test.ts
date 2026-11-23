// **front/ 源码里不许出现身份**（站名 / 品牌名 / 平台名）——它们在缝里，
// 由接口面送来（`GET /api/config`、`GET /api/platforms`）。
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// `new URL("../../", import.meta.url)` 会被 vite 的资源插件改写成 http 地址，
// 所以这里老老实实用 `fileURLToPath`。
const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
const SRC = resolve(REPO, "front", "src");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

/** 身份词表——从缝里的文件读出来，不写死。 */
function tokens(): string[] {
  const found = new Set<string>();

  const site = JSON.parse(
    readFileSync(join(REPO, "platforms", "blog", "site", "data", "site.json"), "utf8"),
  );
  if (site.name) found.add(String(site.name));

  const brand = readFileSync(join(REPO, "video", "config.toml"), "utf8");
  const brandName = brand.match(/^\s*name\s*=\s*"([^"]+)"/m);
  if (brandName) found.add(brandName[1]);
  const brandToken = brand.match(/^\s*token\s*=\s*"([^"]+)"/m);
  if (brandToken) found.add(brandToken[1]);

  const platforms = join(REPO, "platforms");
  for (const dir of readdirSync(platforms)) {
    let text: string;
    try {
      text = readFileSync(join(platforms, dir, "capability.toml"), "utf8");
    } catch {
      continue; // 没有 capability.toml 的目录不是平台
    }
    const id = text.match(/^\s*id\s*=\s*"([^"]+)"/m);
    if (id) found.add(id[1]);
    const name = text.match(/^\s*name\s*=\s*"([^"]+)"/m);
    if (name) found.add(name[1]);
  }

  return [...found].filter((token) => token.length >= 3);
}

/**
 * 匹配规则：**ASCII 词按词边界**，中文词按子串。
 *
 * 平台 id 里有 `blog` / `channels` 这种通用英文词——按子串匹配会误伤
 * （`blogging` 里也有 `blog`），按词边界才准。
 */
function matches(text: string, token: string): boolean {
  if (/^[\x20-\x7e]+$/.test(token)) {
    const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`\\b${escaped}\\b`, "i").test(text);
  }
  return text.includes(token);
}

describe("front/ 的身份缝", () => {
  it("源码里一个实例名都没有", () => {
    const list = tokens();
    expect(list.length).toBeGreaterThan(0);
    const offenders: string[] = [];
    for (const file of walk(SRC).filter((f) => /\.(ts|vue)$/.test(f))) {
      const text = readFileSync(file, "utf8");
      for (const token of list) {
        if (matches(text, token)) offenders.push(`${file}: ${token}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
