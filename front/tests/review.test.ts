// 两条线的信号长得一样，在同一张表里排在一起（规格 G3）。
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import ReviewPanel from "../src/views/ReviewPanel.vue";
import type { ReviewReport } from "../src/api/types";

const report: ReviewReport = {
  subject: { kind: "episode", id: "a/b/c/short", path: "video/episodes/a/b/c/short" },
  layer: "text",
  counts: { error: 1, warn: 2, info: 0 },
  signals: [
    { rule: "VT-07", layer: "text", severity: "error", target: "第3句", line: null, excerpt: "a", detail: "d" },
    { rule: "AIF-01", layer: "document", severity: "warn", target: "第 42 行", line: 42, excerpt: "b", detail: "d" },
  ],
  notes: [],
  gate: { status: "待审", blocking: true, reason: "还没有审校记录" },
};

describe("ReviewPanel", () => {
  it("按 error → warn → info 排信号", () => {
    const wrapper = mount(ReviewPanel, { props: { report, busy: false } });
    const rules = wrapper.findAll("[data-test=signal]").map((n) => n.attributes("data-rule"));
    expect(rules).toEqual(["VT-07", "AIF-01"]);
  });

  it("顶部显示 gate 状态", () => {
    const wrapper = mount(ReviewPanel, { props: { report, busy: false } });
    expect(wrapper.find("[data-test=gate]").text()).toContain("待审");
  });

  it("没有报告时显示一句话，不假装没问题", () => {
    const wrapper = mount(ReviewPanel, { props: { report: null, busy: false } });
    expect(wrapper.find("[data-test=empty]").exists()).toBe(true);
    expect(wrapper.find("[data-test=gate]").exists()).toBe(false);
  });

  it("点一条信号发 locate", async () => {
    const wrapper = mount(ReviewPanel, { props: { report, busy: false } });
    await wrapper.findAll("[data-test=signal] button")[1].trigger("click");
    const emitted = wrapper.emitted("locate");
    expect(emitted).toBeTruthy();
    expect((emitted as any)[0][0].rule).toBe("AIF-01");
  });

  it("三个计数都摆出来", () => {
    const wrapper = mount(ReviewPanel, { props: { report, busy: false } });
    expect(wrapper.find("[data-test=count-error]").text()).toContain("1");
    expect(wrapper.find("[data-test=count-warn]").text()).toContain("2");
  });
});
