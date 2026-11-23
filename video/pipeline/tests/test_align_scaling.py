"""align 的 DP 剪枝：结果必须与穷举一致，但不能慢到不可用。

**背景**
------
`align_by_weight` 是 O(句数 × 片段数²) 的纯 Python DP。实测：

| 句数 | 语音片段 | 穷举耗时 |
| ---: | ---: | ---: |
| 50 | 150 | 0.05 s |
| 200 | 600 | 3.4 s |
| 600 | 1,800 | **95.7 s** |

完整版有 200~600 句，这个规模不能接受。

**剪枝必须「不损质量」**
------------------------
计划原稿的限窗剪枝（只在「理想位置」附近找解）在大规模上**会让答案变差**：
200 句 / 600 片段时 DP 目标从 42052.30 涨到 42189.58。
所以现在走的是**凸包精确剪枝**——复杂度 O(句数 × 片段数)，
600 句 1.2 秒，而且与穷举**逐字相同**（见第一条测试）。

「逐字相同」不是靠对拍碰运气：凸包的选解用**穷举同款代价公式**，
并列时取靠前的 i，与穷举的取舍规则一致。
"""
from __future__ import annotations

import random
import time

from pyv import align


def _spans(count: int, length: float = 1.0, gap: float = 0.2):
    spans = []
    cursor = 0.0
    for _ in range(count):
        spans.append((cursor, cursor + length))
        cursor += length + gap
    return spans


def _speech_durations(spans, pairs) -> list[float]:
    """把对齐结果还原成「每句占了几秒语音」。

    ⚠️ 结果里的 (start, end) 是**墙钟**区间（含片段之间的静音），
    而 DP 的代价用的是**语音时长之和**（片段之间的空隙不算）。
    拿 (end - start) 当语音时长去算误差，量的是另一个东西。
    """
    durations: list[float] = []
    cursor = 0
    for start, end, _ in pairs:
        while cursor < len(spans) and spans[cursor][0] < start - 1e-9:
            cursor += 1
        last = cursor
        while last < len(spans) and spans[last][0] < end - 1e-9:
            last += 1
        durations.append(sum(e - s for s, e in spans[cursor:last]))
        cursor = last
    return durations


def _dp_objective(spans, pairs, weights) -> float:
    """DP 自己的目标函数值：每句「实际语音时长 - 应有时长」的平方和。"""
    total_speech = sum(e - s for s, e in spans)
    total_weight = sum(weights)
    durations = _speech_durations(spans, pairs)
    cumulative_weight = 0.0
    previous = 0.0
    objective = 0.0
    for duration, weight in zip(durations, weights):
        cumulative_weight += weight
        cumulative_time = total_speech * cumulative_weight / total_weight
        target = cumulative_time - previous
        previous = cumulative_time
        objective += (duration - target) ** 2
    return objective


def test_pruned_result_equals_the_exhaustive_one_on_small_inputs():
    """剪枝不是近似——结果必须与穷举逐字相同。"""
    random.seed(7)
    spans = _spans(40)
    texts = [f"第{i}句话" for i in range(12)]
    weights = [random.uniform(5, 30) for _ in texts]

    exhaustive = align.align_by_weight(spans, texts, weights, prune=False)
    pruned = align.align_by_weight(spans, texts, weights)
    assert pruned == exhaustive


def test_the_pruned_dp_objective_equals_the_exhaustive_one():
    """强 guard：两边算出的 **DP 目标值**逐位相等（不只是「差不多」）。

    只比总误差不够——那是另一个量（见 `_total_error` 的说明）。
    这里量的是 DP 真正在优化的那个函数：逐位相等才算没损质量。
    """
    random.seed(13)
    spans = _spans(60)
    texts = [f"第{i}句话" for i in range(18)]
    weights = [random.uniform(5, 30) for _ in texts]

    exhaustive = align.align_by_weight(spans, texts, weights, prune=False)
    pruned = align.align_by_weight(spans, texts, weights)
    assert _dp_objective(spans, pruned, weights) == \
        _dp_objective(spans, exhaustive, weights)


def test_pruning_does_not_make_the_answer_worse():
    """剪枝后的总平方误差不得比穷举更大。"""
    random.seed(11)
    spans = _spans(60)
    texts = [f"第{i}句话" for i in range(18)]
    weights = [random.uniform(5, 30) for _ in texts]

    exhaustive = align.align_by_weight(spans, texts, weights, prune=False)
    pruned = align.align_by_weight(spans, texts, weights)
    assert align._total_error(pruned, texts, weights) <= \
        align._total_error(exhaustive, texts, weights) + 1e-9


def test_the_fast_path_matches_the_exhaustive_one_on_random_inputs():
    """随机输入上反复对拍：剪枝解必须与穷举解一致。

    固定种子，跑得完也跑得稳。覆盖「权重全相等」这种并列最多的情形——
    并列时两边必须挑到同一个（同样好的）解，否则拼接出来的画面会跳。
    """
    for seed in range(24):
        rng = random.Random(seed)
        n_sent = rng.randint(2, 10)
        n_spans = rng.randint(n_sent, n_sent + 12)
        spans = _spans(n_spans, length=rng.choice([1.0, 0.5, 2.0]),
                       gap=rng.choice([0.0, 0.2]))
        texts = [f"第{i}句" for i in range(n_sent)]
        if seed % 3 == 0:
            weights = [10.0] * n_sent          # 全等权重：并列最多
        elif seed % 3 == 1:
            weights = [float(rng.randint(1, 3)) for _ in texts]
        else:
            weights = [rng.uniform(5, 30) for _ in texts]

        exhaustive = align.align_by_weight(spans, texts, weights, prune=False)
        pruned = align.align_by_weight(spans, texts, weights)
        assert pruned == exhaustive, f"seed={seed} 两边不一致"


def test_aligning_six_hundred_sentences_is_fast_enough():
    """600 句（完整版的规模）必须在 15 秒内对齐完。"""
    spans = _spans(1800)
    texts = [f"第{i}句话讲了一个机制" for i in range(600)]
    started = time.time()
    align.align_by_weight(spans, texts)
    elapsed = time.time() - started
    assert elapsed < 15.0, f"600 句对齐用了 {elapsed:.1f} 秒，太慢"


def test_the_unchanged_call_signature_still_works():
    """现有调用方 align_by_weight(spans, texts) 的行为不许变。"""
    spans = _spans(12)
    texts = [f"第{i}句" for i in range(4)]
    result = align.align_by_weight(spans, texts)
    assert len(result) == 4
    assert result[0][2] == texts[0]
