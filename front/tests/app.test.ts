// 门面的接线：新建表单 → 建 → **自动选中**；「起草」按钮 → 501 的原话。
//
// 界面只发 HTTP——这里用假的 fetch 顶上接口面，
// 断言的是**发出去的请求**与**显示出来的字**，不是实现细节。
import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

import App from "../src/App.vue";

const OPTIONS = {
  document: {
    categories: [
      { name: "distributed", children: [{ name: "foundations", children: [] }] },
    ],
  },
  episode: { series: [], tiers: ["short", "mid", "full"] },
};

interface Call {
  url: string;
  method: string;
  body: unknown;
}

/** 假 fetch：按 url 分派，顺便把每次调用记下来。 */
function fakeFetch(
  handler: (url: string, method: string) => { status?: number; body?: unknown },
): { calls: Call[] } {
  const calls: Call[] = [];
  global.fetch = vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET") as string;
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ url, method, body });
    const { status = 200, body: payload = {} } = handler(url, method);
    return {
      ok: status < 400,
      status,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    };
  }) as unknown as typeof fetch;
  return { calls };
}

/** 普通的接口面：草稿箱空的、坐标选项有的、出包快照空的。 */
function plainHandler(url: string) {
  if (url === "/api/drafts") return { body: { units: [] } };
  if (url === "/api/drafts/options") return { body: OPTIONS };
  if (url === "/api/publish/outbox") return { body: { snapshots: [] } };
  return { body: {} };
}

describe("创作平台的门面", () => {
  it("点「新建文档草稿」把表单打开", async () => {
    fakeFetch(plainHandler);
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.find("[data-test='input-slug']").exists()).toBe(false);
    await wrapper.find("button[data-test='create-document']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-test='input-slug']").exists()).toBe(true);
    expect(wrapper.find("[data-test='select-level-0']").exists()).toBe(true);
  });

  it("建好之后刷新列表并**自动选中**新的一稿", async () => {
    const { calls } = fakeFetch((url, method) => {
      if (url === "/api/drafts" && method === "POST") {
        return { body: { kind: "document", draft_id: "distributed/foundations/篇" } };
      }
      return plainHandler(url);
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.find("button[data-test='create-document']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='select-level-0']").setValue("distributed");
    await wrapper.find("[data-test='select-level-1']").setValue("foundations");
    await wrapper.find("[data-test='input-slug']").setValue("篇");
    await wrapper.find("button[data-test='submit']").trigger("click");
    await flushPromises();

    const post = calls.find((c) => c.url === "/api/drafts" && c.method === "POST");
    expect(post?.body).toEqual({
      kind: "document",
      draft_id: "distributed/foundations/篇",
      title: "",
    });
    // 自动选中：接着读了新的一稿。
    expect(calls.some((c) => c.url === "/api/drafts/distributed/foundations/篇")).toBe(true);
  });

  it("「起草（未启用）」按钮把后端的原话报出来", async () => {
    fakeFetch((url) => {
      if (url === "/api/drafts/draft") {
        return {
          status: 501,
          body: { detail: "AI 起草这一版还没做：先手写稿子，或新建一个空白草稿" },
        };
      }
      return plainHandler(url);
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.find("button[data-test='ai-draft']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-test='message']").text()).toBe(
      "AI 起草这一版还没做：先手写稿子，或新建一个空白草稿",
    );
  });

  it("建不出来的时候报后端的话，不假装成功", async () => {
    const { calls } = fakeFetch((url, method) => {
      if (url === "/api/drafts" && method === "POST") {
        return { status: 409, body: { detail: "distributed/foundations/篇 已经在草稿箱里了" } };
      }
      return plainHandler(url);
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.find("button[data-test='create-document']").trigger("click");
    await flushPromises();
    await wrapper.find("[data-test='select-level-0']").setValue("distributed");
    await wrapper.find("[data-test='select-level-1']").setValue("foundations");
    await wrapper.find("[data-test='input-slug']").setValue("篇");
    await wrapper.find("button[data-test='submit']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-test='message']").text()).toBe(
      "distributed/foundations/篇 已经在草稿箱里了",
    );
    // 没建成功 → 不该去读那一稿（更不该显示成建好了）。
    expect(calls.some((c) => c.url === "/api/drafts/distributed/foundations/篇")).toBe(false);
    expect(wrapper.find("[data-test='input-slug']").exists()).toBe(true);
  });
});
