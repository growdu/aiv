"""每个场景模块的**最小 params**。

契约化之后，画面上的字与数字都从 `params` 进来（见 `pyv/params.py`）。
视频线正在清空重来，磁盘上没有期可读，于是测试自己造输入：
**形状照场景代码要的来**（几个字段、什么类型），**内容不算数**。

为什么合成一处：场景模块一多，各测试文件各造一份的话，
形状改一处要改二十几个文件；放在这儿，改一处就够。

**中文词表只从字体里有字形的字里挑**：当前字体缺字形时，
画面上会静默画成豆腐块——`tests/test_scenes.py` 里那条
「画的每个字都要在字体里」的守卫就是守这个的。
"""
from __future__ import annotations

import copy

#: 造 params 用的中文词表。**每个字都得是当前字体里有字形的。**
_WORDS = {
    "title": "第一期",
    "subtitle": "流程线的最小输入",
    "tagline": "格式对就行 · 内容占位",
    "caption": "只看输入格式",
    "badge": "growdu",
    "label": "示例",
    "note": "说明",
    "axis": "顺序",
    "legend": "图例",
    "buffer": "缓冲区",
    "slot": "槽位",
    "question": "做不到的事",
    "conclusion": "所以要小心",
    "conflict": "冲突",
    "compatible": "兼容",
    "memory": "内存",
    "disk": "磁盘",
    "spill": "落盘",
    "serial": "串行解码",
    "parallel": "并行解码",
    "callout": "2–5 倍",
    "callout_sub": "串行是基线",
    "worker": "解码线程",
    "reader": "reader",
    "walsender": "walsender",
    "publisher": "订阅端",
    "apply": "并行 apply",
    "queue": "队列",
    "ddl": "结构化 DDL",
    "wal": "WAL",
    "csn": "CSN",
    "begin": "起点",
    "subscriber": "订阅者",
    "emit": "发出去",
    "target": "接收方",
    "commit": "提交",
    "source": "来源",
    "middle": "中间",
    "layer": "层",
    "tuple": "元组",
    "field": "字段",
    "lock": "加锁",
    "deleted": "删除标记",
    "multixact": "多条锁",
    "core": "核",
    "big": "拉开",
    "small": "很小",
    "stat": "统计",
    "decoder": "解码器",
    "row": "行",
    "table": "表",
    "key": "键",
    "hot": "索引",
    "weak": "弱",
    "strong": "强",
    "left": "持有方",
    "right": "申请方",
    "benefit": "省一次改写",
    "step": "一步",
    "node": "节点",
    "window": "窗口",
    "mode": "模式",
    "row_axis": "已持有的锁",
    "col_axis": "要申请的锁",
    "mode_note": "模式说明",
    "step_note": "这一步做什么",
    "shortfall": "做不到",
    "shortfall_note": "原因",
    "key_title": "冲突键",
    "key_conclusion": "三要素缺一不可",
    "write": "写",
    "write_a": "写 A",
    "write_b": "写 B",
    "ddl_text": "ALTER TABLE t ADD COLUMN c INT",
    "axis_label": "提交顺序",
    "counter_label": "计数器",
    "counter_sub": "先到先得",
    "counter_bits": "64 bit",
    "csn_prefix": "CSN",
    "layer_name": "第 %d 层",
    "layer_role": "角色",
}

#: 事务号。用 ASCII：契约里的事务号就是这种形状。
_TXN = ["T1", "T2", "T3"]
_XID = ["101", "102", "103"]

#: 提交顺序。**故意不等于编号顺序**——这一段讲的就是「先后是乱的」。
#: s02（谁先 commit）与 s03（发号）讲的是同一件事，所以两边共用这一份。
COMMIT_ORDER = ["T2", "T1", "T3"]

#: 事务各自改到哪一行。T1 与 T2 改到同一行——那才是「冲突」。
NODE_NOTES = ["row-1", "row-1", "row-2"]

#: WAL 记录：[位置, 事务, 操作]。
_RECORDS = [
    ["0", "T1", "insert"],
    ["1", "T2", "insert"],
    ["2", "T1", "update"],
    ["3", "T3", "insert"],
    ["4", "T1", "commit"],
    ["5", "T2", "commit"],
]

#: 六层的结构（层号 / 名字 / 角色）。
_LAYERS = [
    ["L1", "接入层", "角色"],
    ["L2", "解析层", "角色"],
    ["L3", "规划层", "角色"],
    ["L4", "改写层", "角色"],
    ["L5", "执行层", "角色"],
    ["L6", "落盘层", "角色"],
]

#: 锁模式矩阵：4×4 的布尔表（True = 兼容）。
_MATRIX = [
    [True, True, True, False],
    [True, True, False, False],
    [True, False, False, False],
    [False, False, False, False],
]

#: 每个场景模块的最小 params。
SCENE_PARAMS: dict[str, dict] = {
    "pyv.scenes.s01_intro": {
        "title": _WORDS["title"],
        "subtitle": _WORDS["subtitle"],
        "tagline": _WORDS["tagline"],
    },
    "pyv.scenes.s02_apply_queue": {
        "title": _WORDS["title"],
        "publisher_label": _WORDS["publisher"],
        "publisher_sub": _WORDS["note"],
        "apply_label": _WORDS["apply"],
        "apply_sub": _WORDS["note"],
        "queue_label": _WORDS["queue"],
        "txn_ids": list(_TXN),
        "active_txn": "T1",
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s02_mixed": {
        "title": _WORDS["title"],
        "axis_label": _WORDS["axis_label"],
        "txn_ids": list(_TXN),
        # 提交顺序刻意不等于编号顺序：这一段讲的就是「先后是乱的」。
        "commit_order": list(COMMIT_ORDER),
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s02_raw_sql": {
        "title": _WORDS["title"],
        "ddl_text": _WORDS["ddl_text"],
        "source_label": _WORDS["source"],
        "wal_label": _WORDS["wal"],
        "target_label": _WORDS["target"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s02_serial": {
        "title": _WORDS["title"],
        "decoder_label": _WORDS["decoder"],
        "decoder_sub": _WORDS["note"],
        "target_label": _WORDS["target"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s02_wal_interleave": {
        "title": _WORDS["title"],
        "axis_label": _WORDS["axis_label"],
        "txn_ids": list(_TXN),
        "records": [list(row) for row in _RECORDS],
        "legend_label": _WORDS["legend"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s02_write_conflict": {
        "title": _WORDS["title"],
        "table_label": _WORDS["table"],
        "row_label": _WORDS["row"],
        "txn_a": "T1",
        "txn_b": "T2",
        "write_a": _WORDS["write_a"],
        "write_b": _WORDS["write_b"],
        "conclusion": _WORDS["conclusion"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s03_conflict_key": {
        "title": _WORDS["title"],
        "table_label": _WORDS["table"],
        "row_labels": ["row-1", "row-2", "row-3"],
        "hot_index": 1,
        "key_title": _WORDS["key_title"],
        "key_parts": ["表", "索引", "键值"],
        "key_values": ["t", "idx", "7"],
        "key_conclusion": _WORDS["key_conclusion"],
        "txn_a": "T1",
        "txn_b": "T2",
        "conflict_label": _WORDS["conflict"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s03_cores": {
        "title": _WORDS["title"],
        "core_count": 32,
        "core_cols": 8,
        "highlighted_core": 3,
        "stat": _WORDS["stat"],
        "big_label": _WORDS["big"],
        "small_label": _WORDS["small"],
        "conclusion": _WORDS["conclusion"],
    },
    "pyv.scenes.s03_counter": {
        "title": _WORDS["title"],
        "counter_label": _WORDS["counter_label"],
        "counter_sub": _WORDS["counter_sub"],
        "counter_bits": _WORDS["counter_bits"],
        "counter_value": "100",
        # 与 s02 共用同一份提交顺序：两段画面讲的是同一组事务。
        "txn_ids": list(COMMIT_ORDER),
        "csn_values": ["101", "102", "103"],
        "csn_prefix": _WORDS["csn_prefix"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s03_lock_modes": {
        "title": _WORDS["title"],
        "left_label": _WORDS["left"],
        "left_note": _WORDS["mode_note"],
        "right_label": _WORDS["right"],
        "right_note": _WORDS["mode_note"],
        "modes": [["KEY SHARE", "KEY SHARE"], ["ROW", "ROW"],
                  ["UPDATE", "UPDATE"], ["EXCLUSIVE", "EXCLUSIVE"]],
        "weak_label": _WORDS["weak"],
        "strong_label": _WORDS["strong"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s03_reorder_buffer": {
        "title": _WORDS["title"],
        "buffer_label": _WORDS["buffer"],
        "txn_ids": list(_TXN),
        "txn_xids": list(_XID),
        "xid_prefix": "XID",
        "records": [list(row) for row in _RECORDS],
        "slot_label": _WORDS["slot"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s03_shortfalls": {
        "title": _WORDS["title"],
        "question_label": _WORDS["question"],
        "shortfalls": [[_WORDS["shortfall"], _WORDS["shortfall_note"]],
                       [_WORDS["shortfall"], _WORDS["shortfall_note"]],
                       [_WORDS["shortfall"], _WORDS["shortfall_note"]],
                       [_WORDS["shortfall"], _WORDS["shortfall_note"]]],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s04_ddl_pipeline": {
        "title": _WORDS["title"],
        "steps": [[_WORDS["step"], _WORDS["step_note"]],
                  [_WORDS["step"], _WORDS["step_note"]],
                  [_WORDS["step"], _WORDS["step_note"]],
                  [_WORDS["step"], _WORDS["step_note"]],
                  [_WORDS["step"], _WORDS["step_note"]]],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s04_dependency_dag": {
        "title": _WORDS["title"],
        "window_label": _WORDS["window"],
        "nodes": list(_TXN),
        "node_notes": list(NODE_NOTES),
        "edges": [["T1", "T2"], ["T2", "T3"]],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s04_lock_matrix": {
        "title": _WORDS["title"],
        "row_axis_label": _WORDS["row_axis"],
        "col_axis_label": _WORDS["col_axis"],
        "mode_labels": [["KEY SHARE"], ["ROW"], ["UPDATE"], ["EXCLUSIVE"]],
        "matrix": [list(row) for row in _MATRIX],
        "compatible_label": _WORDS["compatible"],
        "conflict_label": _WORDS["conflict"],
        "legend_label": _WORDS["legend"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s04_parallel": {
        "title": _WORDS["title"],
        "source_label": _WORDS["reader"],
        "source_sub": _WORDS["note"],
        "worker_count": 4,
        "worker_prefix": _WORDS["worker"],
        "target_label": _WORDS["walsender"],
        "target_sub": _WORDS["note"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s04_propagate": {
        "title": _WORDS["title"],
        "csn_label": _WORDS["csn"],
        "wal_label": _WORDS["wal"],
        "wal_sub": _WORDS["note"],
        "begin_label": _WORDS["begin"],
        "begin_sub": _WORDS["note"],
        "subscriber_label": _WORDS["subscriber"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s04_spill": {
        "title": _WORDS["title"],
        "memory_label": _WORDS["memory"],
        "disk_label": _WORDS["disk"],
        "spill_label": _WORDS["spill"],
        "chips": ["a", "b", "c", "d"],
        "spill_count": 2,
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s05_bench": {
        "title": _WORDS["title"],
        "serial_label": _WORDS["serial"],
        "parallel_label": _WORDS["parallel"],
        "callout": _WORDS["callout"],
        "callout_sub": _WORDS["callout_sub"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s05_ddl_benefit": {
        "title": _WORDS["title"],
        "source_label": _WORDS["source"],
        "source_value": "10",
        "mid_label": _WORDS["middle"],
        "target_label": _WORDS["target"],
        "target_value": "3",
        "benefits": [_WORDS["benefit"], _WORDS["benefit"]],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s05_emit": {
        "title": _WORDS["title"],
        "buffer_label": _WORDS["buffer"],
        "emit_label": _WORDS["emit"],
        "target_label": _WORDS["target"],
        "slots": [["T1", ["insert", "update", "commit"]],
                  ["T2", ["insert", "commit"]]],
        "emit_txn": "T1",
        "commit_op": "commit",
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s05_layers": {
        "title": _WORDS["title"],
        "layer_ids": [row[0] for row in _LAYERS],
        "layer_names": [row[1] for row in _LAYERS],
        "layer_roles": [row[2] for row in _LAYERS],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s05_scheduler": {
        "title": _WORDS["title"],
        "worker_count": 2,
        "worker_prefix": _WORDS["worker"],
        "dispatch": [["T1", 0], ["T2", 1], ["T3", 0]],
        "commit_label": _WORDS["commit"],
        "commit_order": ["T1", "T2", "T3"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s05_tuple_lock": {
        "title": _WORDS["title"],
        "tuple_label": _WORDS["tuple"],
        "field_labels": ["xmin", "xmax"],
        "bit_labels": [["1", "0"], ["0", "1"]],
        "lock_only_label": _WORDS["lock"],
        "deleted_label": _WORDS["deleted"],
        "multixact_label": _WORDS["multixact"],
        "multixact_note": _WORDS["note"],
        "caption": _WORDS["caption"],
    },
    "pyv.scenes.s06_outro": {
        "title": _WORDS["title"],
        "subtitle": _WORDS["subtitle"],
        "badge": _WORDS["badge"],
    },
}


def params_for(module_name: str) -> dict:
    """某个场景模块的最小 params（每次给一份新的，改了不串味）。"""
    return copy.deepcopy(SCENE_PARAMS[module_name])


def words() -> dict:
    """词表（供个别用例改词用）。"""
    return dict(_WORDS)
