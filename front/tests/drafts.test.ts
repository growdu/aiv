// **保存只写草稿箱**（规格 §7.2 铁律 1）：编辑器不许直接写 docs/ 或 video/。
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import DraftPicker from "../src/views/DraftPicker.vue";
import ScriptEditor from "../src/views/ScriptEditor.vue";
import type { DraftUnit } from "../src/api/types";

const unit: DraftUnit = {
  kind: "episode",
  draft_id: "_video/a/b/c/short",
  path: "drafts/_video/a/b/c/short",
  files: ["口播稿.md"],
  promotable: true,
  reason: "",
};

describe("ScriptEditor", () => {
  it("保存时只发出 files 这一个载荷，没有母稿层的入口", async () => {
    const wrapper = mount(ScriptEditor, {
      props: { unit, files: { "口播稿.md": "稿" } },
    });
    await wrapper.find("button[data-test=save]").trigger("click");
    const emits = wrapper.emitted("save");
    expect(emits).toBeTruthy();
    expect(Object.keys((emits as any)[0][0])).toEqual(["口播稿.md"]);
    expect(wrapper.html().includes("/api/documents")).toBe(false);
  });

  it("过审是另一个按钮", () => {
    const wrapper = mount(ScriptEditor, {
      props: { unit, files: { "口播稿.md": "稿" } },
    });
    expect(wrapper.find("button[data-test=promote]").exists()).toBe(true);
  });

  it("不过审的稿子没有过审按钮，只给原因", () => {
    const wrapper = mount(ScriptEditor, {
      props: {
        unit: { ...unit, kind: "index", promotable: false, reason: "索引页这一版不过审" },
        files: { "_index.md": "索引" },
      },
    });
    expect(wrapper.find("button[data-test=promote]").exists()).toBe(false);
    expect(wrapper.html()).toContain("索引页这一版不过审");
  });

  it("两个 episode 字段各带一行说明，不混在一处", () => {
    const wrapper = mount(ScriptEditor, {
      props: {
        unit: { ...unit, files: ["口播稿.md", "contract.json", "publish.json"] },
        files: {
          "口播稿.md": "稿",
          "contract.json": "{}",
          "publish.json": "{}",
        },
      },
    });
    const text = wrapper.text();
    expect(text).toContain("文档路径");
    expect(text).toContain("期路径");
  });
});

describe("DraftPicker", () => {
  const units: DraftUnit[] = [
    { kind: "document", draft_id: "distributed/a", path: "drafts/distributed",
      files: ["a.md"], promotable: true, reason: "" },
    { kind: "index", draft_id: "distributed/_index", path: "drafts/distributed",
      files: ["_index.md"], promotable: false, reason: "索引页这一版不过审" },
  ];

  it("按 kind 分组，索引页单列并标原因", () => {
    const wrapper = mount(DraftPicker, { props: { units } });
    const text = wrapper.text();
    expect(text).toContain("文档稿");
    expect(text).toContain("索引页");
    expect(text).toContain("索引页这一版不过审");
  });

  it("搜索按 draft_id 过滤", async () => {
    const wrapper = mount(DraftPicker, { props: { units } });
    await wrapper.find("input[data-test=search]").setValue("_index");
    expect(wrapper.find("[data-test='unit-distributed/a']").exists()).toBe(false);
    expect(wrapper.find("[data-test='unit-distributed/_index']").exists()).toBe(true);
  });

  it("当前选中的那一行标出来", async () => {
    const wrapper = mount(DraftPicker, {
      props: { units, selected: "distributed/a" },
    });
    const active = wrapper.findAll(".picker__item--active");
    expect(active.length).toBe(1);
    expect(active[0].attributes("data-test")).toBe("unit-distributed/a");
  });

  it("选一行发 select，新建发 create", async () => {
    const wrapper = mount(DraftPicker, { props: { units } });
    await wrapper.find("[data-test='unit-distributed/a']").trigger("click");
    expect(wrapper.emitted("select")?.[0]).toEqual(["distributed/a"]);
    await wrapper.find("button[data-test=create-episode]").trigger("click");
    expect(wrapper.emitted("create")?.[0]).toEqual(["episode"]);
  });
});
