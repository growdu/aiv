"""字幕事件定位：二分版必须与线性版逐次相同。

**背景**
------
`event_at` 每帧都从第一条字幕扫起。完整版有 600 条字幕 × 5 万帧
= 3,000 万次比较，纯 Python 跑一遍要几十秒。

**语义不许变**
--------------
二分只认「字幕事件不重叠」这一条。事件重叠时二分会挑到另一条，
所以那种输入必须退回线性扫——**语义与从前完全一样**，
不能因为换了实现就换个答案（最后一条测试盯着这件事）。
"""
from __future__ import annotations

import random
import time

from pyv import subtitle
from pyv.timeline import SubtitleEvent, SubtitleStyle


def _style() -> SubtitleStyle:
    return SubtitleStyle(primary="#1B2A47", outline="#FFFFFF")


def _events(count: int):
    events = []
    cursor = 0.0
    for index in range(count):
        start = cursor
        end = cursor + 1.5
        cursor = end + 0.25
        events.append(SubtitleEvent(start=start, end=end, text=f"第{index}句"))
    return events


def _linear_lookup(events, t):
    for event in events:
        if event.start <= t < event.end:
            return event
    return None


class _CountingEvent:
    """包一层字幕事件：每次读 start / end 都记账。

    用来数「定位到底看了多少条字幕」——比计时可靠：
    计时阈值会被机器快慢左右，访问次数不会。
    """

    def __init__(self, event: SubtitleEvent) -> None:
        self._event = event
        self.reads = 0

    @property
    def start(self) -> float:
        self.reads += 1
        return self._event.start

    @property
    def end(self) -> float:
        self.reads += 1
        return self._event.end

    @property
    def text(self) -> str:
        return self._event.text


def test_the_lookup_does_not_scan_every_subtitle():
    """定位不能扫全部字幕——600 条 × 5 万帧，线性扫是 3,000 万次比较。

    ⚠️ **光看计时抓不住**：本机线性扫 5 万次只要 0.54 秒，
    落在「2 秒以内」的阈值里——换不换实现都绿。
    所以这里数**属性访问次数**：二分每次只看一条，
    线性扫每次要看几十上百条，一眼就分得出来。
    """
    events = [_CountingEvent(e) for e in _events(600)]
    burner = subtitle.SubtitleBurner(events, _style())
    for event in events:
        event.reads = 0          # 构造期（排序、抽 starts）的读取不算
    for index in range(1000):
        burner.event_at(index * 0.05)
    total = sum(event.reads for event in events)
    assert total < 10000, f"1000 次查找读了 {total} 次属性——定位在扫全部字幕"



def test_bisect_lookup_matches_the_linear_one():
    """逐个时刻对比两种实现，结果必须完全一致。"""
    random.seed(3)
    events = _events(200)
    burner = subtitle.SubtitleBurner(events, _style())
    for _ in range(2000):
        t = random.uniform(-1.0, events[-1].end + 1.0)
        assert burner.event_at(t) == _linear_lookup(events, t)


def test_lookup_is_fast_for_a_long_video():
    """5 万帧 × 600 条字幕，查找必须快到可以忽略。"""
    events = _events(600)
    burner = subtitle.SubtitleBurner(events, _style())
    started = time.time()
    for index in range(50000):
        burner.event_at(index * 0.024)
    elapsed = time.time() - started
    assert elapsed < 2.0, f"5 万次查找用了 {elapsed:.1f} 秒，太慢"


def test_a_time_outside_every_event_returns_none():
    events = _events(3)
    burner = subtitle.SubtitleBurner(events, _style())
    assert burner.event_at(-5.0) is None
    assert burner.event_at(100.0) is None


def test_overlapping_events_keep_the_linear_semantics():
    """事件重叠时仍是「第一条命中的」——换实现不许换答案。

    二分只能处理不重叠的事件；重叠时必须退回线性扫，
    否则 t=2.0 会从「甲」变成「乙」。
    """
    events = [
        SubtitleEvent(start=0.0, end=10.0, text="甲"),
        SubtitleEvent(start=1.0, end=5.0, text="乙"),
    ]
    burner = subtitle.SubtitleBurner(events, _style())
    assert burner.event_at(2.0).text == "甲"
    assert burner.event_at(2.0) == _linear_lookup(events, 2.0)


def test_the_first_event_still_wins_at_its_own_start():
    """边界：t 正好落在某条的 start 上，那条就该命中。"""
    events = _events(4)
    burner = subtitle.SubtitleBurner(events, _style())
    for event in events:
        assert burner.event_at(event.start) == event
        assert burner.event_at(event.end - 1e-9) == event
