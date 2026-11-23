// **front/ 是纯客户端**（规格 D6 / 反目标 A1）：它不许 import 任何后端模块。
// 相对 import 必须解析到 front/src/ 之内；绝对（以 / 开头）import 同理。
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

// `new URL("../src/", import.meta.url)` 会被 vite 的资源插件改写成 http 地址，
// 所以这里老老实实用 `fileURLToPath`。
const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..", "src") + sep;

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

describe("front/ 的缝", () => {
  it("src/ 里的 import 不许跑出 src/", () => {
    const offenders: string[] = [];
    for (const file of walk(SRC).filter((f) => /\.(ts|vue)$/.test(f))) {
      const text = readFileSync(file, "utf8");
      for (const match of text.matchAll(/from\s+["']([^"']+)["']/g)) {
        const spec = match[1];
        if (!spec.startsWith(".") && !spec.startsWith("/")) continue;
        const base = spec.startsWith("/")
          ? join(SRC, spec)
          : resolve(dirname(file), spec);
        if (!base.startsWith(SRC)) offenders.push(`${file}: ${spec}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("绝对 import 指向的文件真的在 src/ 里（不许指向仓库别处）", () => {
    const offenders: string[] = [];
    for (const file of walk(SRC).filter((f) => /\.(ts|vue)$/.test(f))) {
      const text = readFileSync(file, "utf8");
      for (const match of text.matchAll(/from\s+["'](\/[^"']+)["']/g)) {
        const target = join(SRC, match[1]);
        if (!target.startsWith(SRC) || !statSync(target).isFile()) {
          offenders.push(`${file}: ${match[1]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
