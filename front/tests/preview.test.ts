// 产物 URL 必须是 API 的 URL，不是文件系统路径。
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import { artifactURL, eventURL } from "../src/api/client";
import PublishStatus from "../src/views/PublishStatus.vue";
import VideoPreview from "../src/views/VideoPreview.vue";

describe("产物与作业的 URL", () => {
  it("产物 URL 保留斜杠", () => {
    expect(artifactURL("video/out/a-b-c-short.mp4")).toBe(
      "/api/artifacts/video/out/a-b-c-short.mp4",
    );
  });

  it("作业事件 URL 指向 SSE", () => {
    expect(eventURL("j-0007")).toBe("/api/jobs/j-0007/events");
  });
});

describe("PublishStatus", () => {
  it("一张表，列固定", () => {
    const wrapper = mount(PublishStatus, {
      props: {
        snapshots: [
          {
            platform: "p1",
            status: "已出包",
            title: "标题",
            updated_at: "2026-11-23",
            content_id: "x",
          },
        ],
      },
    });
    const heads = wrapper.findAll("th").map((n) => n.text());
    expect(heads).toEqual(["平台", "状态", "标题", "更新时间", "地址"]);
    expect(wrapper.text()).toContain("p1");
  });

  it("没有快照就说没有", () => {
    const wrapper = mount(PublishStatus, { props: { snapshots: [] } });
    expect(wrapper.find("[data-test=empty]").exists()).toBe(true);
  });
});

describe("VideoPreview", () => {
  it("有一个出片按钮", () => {
    const wrapper = mount(VideoPreview, { props: { episode: "a/b/c/short" } });
    expect(wrapper.find("button[data-test=build]").exists()).toBe(true);
  });
});
