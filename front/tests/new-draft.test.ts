// 「新建草稿」的表单：坐标是**由目录树驱动**的，不是写死的层数。
//
// 目录即接口——树的深度是仓库的深度（源向线比扁平稿深两级），
// 所以表单一层一层往下走，树里没了就停下填期号。
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import NewDraftForm from "../src/views/NewDraftForm.vue";
import type { DraftOptions } from "../src/api/types";

const options: DraftOptions = {
  document: {
    categories: [
      {
        name: "distributed",
        children: [{ name: "foundations", children: [] }],
      },
      {
        name: "source-tracks",
        children: [
          {
            name: "postgresql",
            children: [{ name: "getting-started", children: [] }],
          },
        ],
      },
    ],
  },
  episode: {
    series: [
      {
        name: "AIV",
        children: [
          { name: "合集", children: [{ name: "文档", children: [] }] },
        ],
      },
    ],
    tiers: ["short", "mid", "full"],
  },
};

async function pick(wrapper: any, level: number, value: string) {
  await wrapper.find(`[data-test='select-level-${level}']`).setValue(value);
}

describe("NewDraftForm", () => {
  it("文档流：选分类 → 选二级 → 填期号，拼出坐标", async () => {
    const wrapper = mount(NewDraftForm, { props: { kind: "document", options } });

    // 初始只有一级下拉（分类）——后面的层等前面选了才出现。
    expect(wrapper.find("[data-test='select-level-0']").exists()).toBe(true);
    expect(wrapper.find("[data-test='select-level-1']").exists()).toBe(false);

    await pick(wrapper, 0, "distributed");
    expect(wrapper.find("[data-test='select-level-1']").exists()).toBe(true);

    await pick(wrapper, 1, "foundations");
    await wrapper.find("[data-test='input-slug']").setValue("篇");
    await wrapper.find("[data-test='input-title']").setValue("标题");
    await wrapper.find("button[data-test='submit']").trigger("click");

    expect(wrapper.emitted("submit")?.[0][0]).toEqual({
      kind: "document",
      draft_id: "distributed/foundations/篇",
      title: "标题",
    });
  });

  it("树的深度不写死：源向线深两级就多两级下拉", async () => {
    const wrapper = mount(NewDraftForm, { props: { kind: "document", options } });

    await pick(wrapper, 0, "source-tracks");
    expect(wrapper.find("[data-test='select-level-2']").exists()).toBe(false);
    await pick(wrapper, 1, "postgresql");
    expect(wrapper.find("[data-test='select-level-2']").exists()).toBe(true);
    await pick(wrapper, 2, "getting-started");

    await wrapper.find("[data-test='input-slug']").setValue("篇");
    await wrapper.find("button[data-test='submit']").trigger("click");

    expect(wrapper.emitted("submit")?.[0][0]).toEqual({
      kind: "document",
      draft_id: "source-tracks/postgresql/getting-started/篇",
      title: "",
    });
  });

  it("「＋ 新建一级」把那一层换成文本框", async () => {
    const wrapper = mount(NewDraftForm, { props: { kind: "document", options } });

    await pick(wrapper, 0, "__new__");
    expect(wrapper.find("[data-test='input-level-0']").exists()).toBe(true);

    await wrapper.find("[data-test='input-level-0']").setValue("新分类");
    // 新分类底下没有子目录 → 第二级也是文本框。
    expect(wrapper.find("[data-test='input-level-1']").exists()).toBe(true);
    await wrapper.find("[data-test='input-level-1']").setValue("新二级");
    await wrapper.find("[data-test='input-slug']").setValue("新篇");

    await wrapper.find("button[data-test='submit']").trigger("click");
    expect(wrapper.emitted("submit")?.[0][0]).toEqual({
      kind: "document",
      draft_id: "新分类/新二级/新篇",
      title: "",
    });
  });

  it("视频流：三层目录 + 档位，坐标带 `_video/` 前缀", async () => {
    const wrapper = mount(NewDraftForm, { props: { kind: "episode", options } });

    await pick(wrapper, 0, "AIV");
    await pick(wrapper, 1, "合集");
    await pick(wrapper, 2, "文档");

    const tiers = wrapper.find("[data-test='select-tier']").findAll("option");
    expect(tiers.map((o) => o.text())).toEqual(["short", "mid", "full"]);

    await wrapper.find("[data-test='select-tier']").setValue("short");
    await wrapper.find("button[data-test='submit']").trigger("click");

    expect(wrapper.emitted("submit")?.[0][0]).toEqual({
      kind: "episode",
      draft_id: "_video/AIV/合集/文档/short",
      title: "",
    });
  });

  it("层没填全时不摆坐标——不摆一个残缺的", async () => {
    const wrapper = mount(NewDraftForm, { props: { kind: "episode", options } });
    // 一层都没填，只选了档位。
    await wrapper.find("[data-test='select-tier']").setValue("short");
    expect(wrapper.find("[data-test='preview']").exists()).toBe(false);

    await pick(wrapper, 0, "AIV");
    await pick(wrapper, 1, "合集");
    await pick(wrapper, 2, "文档");
    expect(wrapper.find("[data-test='preview']").text()).toBe(
      "drafts/_video/AIV/合集/文档/short",
    );
  });

  it("坐标没填全就不许提交", async () => {
    const wrapper = mount(NewDraftForm, { props: { kind: "document", options } });
    await pick(wrapper, 0, "distributed");
    await pick(wrapper, 1, "foundations");
    // 没填期号。
    expect(
      (wrapper.find("button[data-test='submit']").element as HTMLButtonElement).disabled,
    ).toBe(true);
    await wrapper.find("button[data-test='submit']").trigger("click");
    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  it("提醒一句：开一级目录是策展动作", () => {
    const wrapper = mount(NewDraftForm, { props: { kind: "document", options } });
    expect(wrapper.find("[data-test='note']").text()).toContain("策展");
  });

  it("取消是另一个按钮", async () => {
    const wrapper = mount(NewDraftForm, { props: { kind: "document", options } });
    await wrapper.find("button[data-test='cancel']").trigger("click");
    expect(wrapper.emitted("cancel")).toBeTruthy();
  });
});
