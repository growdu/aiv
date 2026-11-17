"""视频审核：成片背后的文本 → 成片本身。

两层，分工不同：

- **文本层**（`VT-*`）审「要讲什么」：口播稿、字幕表、画面契约、母稿与数字出处。
- **成片层**（`VV-*`）审「做出来是什么样」：抽帧看画面，查音轨，查技术参数。

**两层都只出信号，不下结论。**「这句像不像人讲」「这张图讲清了没有」
需要上下文和眼睛，由人和 Agent 判断，结论落在 `aiv/review/episodes/<EP>.md`。

规范在 `aiv/review/README.md`，设计在
`aiv/review/specs/2026-11-16-video-review-design.md`。

**不静默跳过**：产物不在本机时，报告里写一条 note 说清跳过了哪条规则。
「没查」和「查了没问题」是两件事，混起来就成了假装绿。
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from pyv import align
from pyv import contract as contract_mod
from pyv import episodes
from pyv import persona
from pyv import topics
from pyv.timeline import Scene, Storyboard

AIV_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = AIV_ROOT.parent
REVIEW_DIR = AIV_ROOT / "review"
FRAMES_DIR = REVIEW_DIR / "frames"

TEXT_LAYER = "text"
VIDEO_LAYER = "video"

WARN = "warn"
INFO = "info"
ERROR = "error"

TEXT_RULES = ("VT-01", "VT-02", "VT-03", "VT-04", "VT-05", "VT-06", "VT-07")
VIDEO_RULES = ("VV-01", "VV-02", "VV-03", "VV-04", "VV-05", "VV-06", "VV-07")

# ---------------------------------------------------------------- 词表与阈值
#
# **与 `tools/review-check.py`（文档侧检查器）同一份字面量。**
#
# 抄一份而不是 import：`tools/` 不是包，跨目录 import 靠 sys.path 补丁，
# 那是最容易在换机器时断掉的接缝。一致性由
# `aiv/pipeline/tests/test_review.py` 的两条测试钉住——改一边，另一边会红。
#
# 阈值同理：写成字面量，一致性单独钉住。生产常量一改守卫跟着改，
# 守卫就永远是绿的。

CONNECTORS = ("首先", "其次", "最后", "此外", "值得注意的是",
              "总而言之", "综上所述", "总的来说", "事实上")
CONNECTOR_RATIO = 0.15

VAGUE_WORDS = ("高效", "全面", "显著", "至关重要", "强大", "极大",
               "非常好", "行业领先", "完美")

GENERIC_ENDINGS = ("希望本文", "本文到此结束", "以上就是", "让我们一起")
GENERIC_ENDING_RE = re.compile(r"随着.{0,20}的发展")

DUPLICATE_THRESHOLD = 0.85
DUPLICATE_MIN_LEN = 12
DUPLICATE_MIN_CJK = 15
CJK_RE = re.compile(r"[一-鿿]")

#: 数字短语：数字 + 可选单位。**单位表是手挑的**——「个」「次」「行」太常见，
#: 收进来会让几乎每句都命中「有数字」，规则就废了。
UNIT_CHARS = "核位倍秒毫秒层页万亿%‰"
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
NUMBER_PHRASE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([" + UNIT_CHARS + r"])?")

#: 帧的像素标准差低于这个值 → 近乎纯色（黑场/漏画）。
BLANK_FRAME_STDDEV = 3.0
#: 字幕带（画面底部这一段）里暗色像素的占比低于这个值 → 字幕可能没烧上。
SUBTITLE_BAND_RATIO = 0.16
SUBTITLE_DARK_LUMA = 110
SUBTITLE_DARK_RATIO = 0.0008
#: 每个视觉段抽几帧、在段的哪个位置抽。
#:
#: **为什么不止段中点一帧**：实测 `s02` 的段中点（9.524 s）上，结论框已经
#: 画出来了，框里的字却还没显影——结论在段内 48% 处才开始淡入，
#: 84% 才完全显影，段中点正好落在淡入的第一帧（alpha ≈ 0.17）。
#: 只抽中点，审核就会把「动画中间态」当成「漏字」。
#: 段尾帧（85%）补上这个洞。
SCENE_FRAME_POINTS = (("mid", 0.50), ("late", 0.85))
#: 正文区间里旁白静音超过这个秒数 → warn。
#:
#: **0.6 s 是拍脑袋的，实测不是。** 六期旁白共 74 处句间间隙，全部落在
#: 0.25~0.748 s，中位数 0.427 s——0.6 s 卡在自然分布的尾巴里，
#: 会把约两成的正常换气报成「静音」。
#:
#: 1.0 s 比实测最大值高 34%，远小于一句口播的中位时长 2.17 s——
#: 它只会在「少了一句」的时候响。一致性由
#: `test_narration_gaps_stay_below_the_silence_threshold` 钉住。
NARRATION_SILENCE_S = 1.0
#: 成片时长与时间轴的容差。
DURATION_TOLERANCE_S = 0.15
#: 品牌片边界的容差：半帧多一点（24fps 一帧约 0.042 s）。
BRAND_EDGE_TOLERANCE_S = 0.05
#: 关键帧最大间隔（B站《文件上传预处理》：至少 10 秒一个）。
MAX_KEYFRAME_GAP_S = 10.0


# ---------------------------------------------------------------- 数据结构


@dataclass(frozen=True)
class Signal:
    """一条审核信号。只标位置与判据，不下结论。"""

    rule: str
    layer: str
    severity: str
    target: str
    excerpt: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "layer": self.layer,
            "severity": self.severity,
            "target": self.target,
            "excerpt": self.excerpt,
            "detail": self.detail,
        }

    def __str__(self) -> str:
        return f"{self.rule} [{self.severity}] {self.target} {self.detail}"


@dataclass
class Report:
    """一层的审核结论。"""

    episode: str
    layer: str
    signals: list[Signal] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, signal: Signal) -> None:
        self.signals.append(signal)

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def counts(self) -> dict:
        counts = {"error": 0, "warn": 0, "info": 0}
        for signal in self.signals:
            counts[signal.severity] = counts.get(signal.severity, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "episode": self.episode,
            "layer": self.layer,
            "counts": self.counts(),
            "signals": [s.to_dict() for s in self.signals],
            "notes": list(self.notes),
        }

    def summary(self) -> str:
        counts = self.counts()
        lines = [f"{self.episode} · {self.layer} 层："
                 f"{counts['error']} 错 / {counts['warn']} 警 / {counts['info']} 提示"]
        for signal in self.signals:
            lines.append(f"  {signal.severity.upper():5} {signal.rule}  "
                         f"{signal.target}  {signal.detail}")
        for note in self.notes:
            lines.append(f"  ·  {note}")
        if not self.signals and not self.notes:
            lines.append("  （无信号）")
        return "\n".join(lines)


@dataclass
class Materials:
    """文本层的全部输入。"""

    episode: str
    ep_number: str
    title: str
    sentences: list[str]
    subtitles: list[str]
    segments: list[contract_mod.Segment]
    motherdocs: list[Path]
    evidence: list[tuple[str, str, str]]
    notes: list[str] = field(default_factory=list)


@dataclass
class Media:
    """成片层的全部输入。"""

    episode: str
    video: Path | None
    storyboard: Storyboard | None
    narration: Path | None
    bgm: Path | None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Frame:
    """一帧抽帧。"""

    index: int
    time: float
    scene_id: str
    path: Path
    kind: str          # "scene"（段中点）/"late"（段尾）/"keyframe"（编码关键帧）
    subtitle: str = ""
    expected: str = ""

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "time": round(self.time, 3),
            "scene_id": self.scene_id,
            "kind": self.kind,
            "path": str(self.path),
            "subtitle": self.subtitle,
            "expected": self.expected,
        }


# ---------------------------------------------------------------- 工具


def _excerpt(text: str, limit: int = 60) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def _run(cmd: list[str]) -> tuple[int, str, str] | None:
    """跑一条命令。**工具不在时返回 None**，让调用方记 note 而不是炸。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return None
    return proc.returncode, proc.stdout, proc.stderr


def _probe_duration(path: str | Path) -> float | None:
    result = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                   "-of", "csv=p=0", str(path)])
    if result is None or result[0] != 0:
        return None
    try:
        return float(result[1].strip())
    except ValueError:
        return None


# ---------------------------------------------------------------- 文本层


def load_materials(episode: str) -> Materials:
    """装齐文本层的输入。

    口播稿与字幕表来自 `aiv/字幕-<主题>.md`，契约来自 `aiv/contracts/<EP>.json`，
    母稿与数字出处来自 `aiv/选题库.md` 的对应期。
    """
    script_path = episodes.script_path(episode)
    contract_path = episodes.contract_path(episode)
    contract = contract_mod.load_contract(contract_path)
    sentences = align.parse_script(script_path)
    subtitles = align.parse_subtitle_table(script_path)

    notes: list[str] = []
    ep_number = episodes.EP_NUMBERS.get(episode, "")
    motherdocs: list[Path] = []
    evidence: list[tuple[str, str, str]] = []
    title = contract.title

    topic = None
    try:
        for candidate in topics.parse_topics():
            if candidate.fields.get("id") == ep_number:
                topic = candidate
                break
    except (OSError, ValueError) as exc:
        notes.append(f"选题库读不出来（{exc}）：VT-05 数字出处检查跳过")

    if topic is None:
        notes.append(
            f"选题库里找不到 {ep_number}：VT-05 数字出处检查跳过"
            "（口播里的数字没有母稿可比对）")
    else:
        title = topic.title or title
        for relative, _what in topic.docs:
            path = REPO_ROOT / relative
            if path.is_file():
                motherdocs.append(path)
            else:
                notes.append(f"关联文档不存在，VT-05 少一个比对来源：{relative}")
        evidence = list(topic.evidence)

    return Materials(
        episode=episode,
        ep_number=ep_number,
        title=title,
        sentences=sentences,
        subtitles=subtitles,
        segments=list(contract.segments),
        motherdocs=motherdocs,
        evidence=evidence,
        notes=notes,
    )


def _number_phrases(text: str) -> list[tuple[str, str]]:
    """抽出文本里的「数字 + 单位」短语。

    **只收有意义的数字**：两位及以上的，或带单位的。
    一位数没单位（「第 3 期」）几乎必然在母稿里出现，报了也是噪声。
    """
    found: list[tuple[str, str]] = []
    for match in NUMBER_PHRASE_RE.finditer(text):
        number, unit = match.group(1), match.group(2) or ""
        if len(number.replace(".", "")) < 2 and not unit:
            continue
        found.append((number, unit))
    return found


def _corpus_numbers(materials: Materials) -> set[str]:
    """母稿与出处表里出现过的所有数字。

    比对的是**数字集合**，不是子串——「5」不该被「15」满足。
    """
    corpus: set[str] = set()
    for path in materials.motherdocs:
        try:
            corpus.update(NUMBER_RE.findall(path.read_text(encoding="utf-8")))
        except OSError:
            continue
    for statement, source, _note in materials.evidence:
        corpus.update(NUMBER_RE.findall(statement))
        corpus.update(NUMBER_RE.findall(source))
    return corpus


def vt_01_connectors(materials: Materials) -> list[Signal]:
    """句首以结构连接词开头的句占比过高。

    只认句首：句中的「最后」不是结构连接词。
    """
    sentences = materials.sentences
    if not sentences:
        return []
    hits = []
    for index, sentence in enumerate(sentences, 1):
        for word in CONNECTORS:
            if sentence.startswith(word):
                hits.append((index, word))
                break
    ratio = len(hits) / len(sentences)
    if ratio <= CONNECTOR_RATIO:
        return []
    detail = (f"{len(hits)}/{len(sentences)} 句以连接词开头（{ratio:.0%}）："
              + "、".join(f"第{index}句 {word}" for index, word in hits[:8]))
    return [Signal("VT-01", TEXT_LAYER, WARN, f"第{hits[0][0]}句",
                   _excerpt(sentences[hits[0][0] - 1]), detail)]


def vt_02_vague(materials: Materials) -> list[Signal]:
    """空泛评价，且句中没有数字支撑。"""
    hits = []
    for index, sentence in enumerate(materials.sentences, 1):
        for word in VAGUE_WORDS:
            if word not in sentence:
                continue
            if NUMBER_RE.search(sentence):
                continue
            hits.append((index, word))
            break
    if not hits:
        return []
    detail = (f"{len(hits)} 处空泛评价无数字支撑："
              + "、".join(f"第{index}句 {word}" for index, word in hits[:8]))
    return [Signal("VT-02", TEXT_LAYER, WARN, f"第{hits[0][0]}句",
                   _excerpt(materials.sentences[hits[0][0] - 1]), detail)]


def vt_03_generic_ending(materials: Materials) -> list[Signal]:
    """结尾三句出现泛化收尾语。"""
    sentences = materials.sentences
    if len(sentences) < 2:
        return []
    tail_start = max(0, len(sentences) - 3)
    hits = []
    for offset, sentence in enumerate(sentences[tail_start:]):
        index = tail_start + offset + 1
        for word in GENERIC_ENDINGS:
            if word in sentence:
                hits.append((index, word))
                break
        else:
            match = GENERIC_ENDING_RE.search(sentence)
            if match:
                hits.append((index, "随着…的发展"))
    if not hits:
        return []
    detail = ("结尾出现泛化收尾语："
              + "、".join(f"第{index}句 {word}" for index, word in hits))
    return [Signal("VT-03", TEXT_LAYER, WARN, f"第{hits[0][0]}句",
                   _excerpt(sentences[hits[0][0] - 1]), detail)]


def vt_04_duplicate(materials: Materials) -> list[Signal]:
    """近似重复句。"""
    sentences = materials.sentences
    buckets: dict[int, list[tuple[int, str]]] = {}
    for index, sentence in enumerate(sentences, 1):
        text = sentence.strip()
        if len(text) < DUPLICATE_MIN_LEN:
            continue
        if len(CJK_RE.findall(text)) < DUPLICATE_MIN_CJK:
            continue
        buckets.setdefault(len(text) // 5, []).append((index, text))
    pairs = []
    for group in buckets.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                similarity = difflib.SequenceMatcher(
                    None, group[i][1], group[j][1]).ratio()
                if similarity >= DUPLICATE_THRESHOLD:
                    pairs.append((group[i][0], group[j][0], similarity))
    if not pairs:
        return []
    detail = (f"{len(pairs)} 对近似重复句："
              + "、".join(f"第{a}句~第{b}句({sim:.2f})" for a, b, sim in pairs[:5]))
    return [Signal("VT-04", TEXT_LAYER, WARN, f"第{pairs[0][0]}句",
                   _excerpt(sentences[pairs[0][0] - 1]), detail)]


def vt_05_number_evidence(materials: Materials) -> list[Signal]:
    """口播里的数字在母稿与出处表里找不到。"""
    if not materials.motherdocs and not materials.evidence:
        return []
    corpus = _corpus_numbers(materials)
    if not corpus:
        return []
    hits = []
    for index, sentence in enumerate(materials.sentences, 1):
        for number, unit in _number_phrases(sentence):
            if number in corpus:
                continue
            hits.append((index, number, unit))
    if not hits:
        return []
    detail = (f"{len(hits)} 个数字在母稿与出处表里找不到："
              + "、".join(f"第{index}句 {number}{unit}"
                         for index, number, unit in hits[:8]))
    return [Signal("VT-05", TEXT_LAYER, WARN, f"第{hits[0][0]}句",
                   _excerpt(materials.sentences[hits[0][0] - 1]), detail)]


def vt_06_subtitle_drops_number(materials: Materials) -> list[Signal]:
    """口播句里的数字，在对应字幕里丢了。

    口播说了「提升 2 到 5 倍」，字幕写成「性能提升明显」——
    数字在字幕这一层没了，观众看到的是一句空话。
    """
    hits = []
    for index, sentence in enumerate(materials.sentences):
        if index >= len(materials.subtitles):
            break
        subtitle = materials.subtitles[index]
        subtitle_numbers = set(NUMBER_RE.findall(subtitle))
        missing = []
        for number, _unit in _number_phrases(sentence):
            if number not in subtitle_numbers:
                missing.append(number)
        if missing:
            hits.append((index + 1, missing, subtitle))
    if not hits:
        return []
    detail = (f"{len(hits)} 句的数字没进字幕："
              + "、".join(f"第{index}句缺{'/'.join(numbers)}"
                         for index, numbers, _ in hits[:8]))
    return [Signal("VT-06", TEXT_LAYER, WARN, f"第{hits[0][0]}句",
                   _excerpt(hits[0][2]), detail)]


def vt_07_subtitle_format(materials: Materials) -> list[Signal]:
    """字幕表（**源文件**）里的禁止词与超宽行。

    **查的是源文件，不是 storyboard。** `make validate` 查的是上一次
    `align` 出来的 storyboard——源字幕表改了但还没重跑 `align` 时，
    那个门禁看到的还是旧字幕。改完稿没重跑 align 就出片，是最常见的
    「改了但没生效」。

    阈值与判据来自 `pyv/timeline.py`（唯一一份），这里只做遍历。
    """
    from pyv import timeline

    hits = []
    for index, subtitle in enumerate(materials.subtitles, 1):
        lowered = subtitle.lower()
        for word in timeline.BANNED_SUBSTRINGS:
            if word.lower() in lowered:
                hits.append((index, ERROR, f"含禁止词 {word!r}", subtitle))
                break
        for line in subtitle.splitlines():
            stripped = line.strip()
            width = timeline.display_width(stripped)
            if width > timeline.MAX_SUBTITLE_LINE:
                hits.append((index, ERROR,
                             f"单行视觉宽度 {width:.1f} 超过 "
                             f"{timeline.MAX_SUBTITLE_LINE}", subtitle))
    if not hits:
        return []
    detail = (f"{len(hits)} 处字幕表格式问题："
              + "、".join(f"第{index}句 {why}"
                         for index, _severity, why, _text in hits[:8]))
    return [Signal("VT-07", TEXT_LAYER, hits[0][1], f"第{hits[0][0]}句",
                   _excerpt(hits[0][3]), detail)]


TEXT_CHECKS = (
    vt_01_connectors,
    vt_02_vague,
    vt_03_generic_ending,
    vt_04_duplicate,
    vt_05_number_evidence,
    vt_06_subtitle_drops_number,
    vt_07_subtitle_format,
)


def check_text(episode: str) -> Report:
    """跑文本层。"""
    materials = load_materials(episode)
    report = Report(episode=episode, layer=TEXT_LAYER)
    for note in materials.notes:
        report.note(note)
    for check in TEXT_CHECKS:
        for signal in check(materials):
            report.add(signal)
    # 人格 9 条并入报告：审校记录里人格结论与信号同表，
    # 但**不重写**——判据只有一份（pyv/persona.py）。
    try:
        script_path = episodes.script_path(episode)
        findings = persona.check_file(script_path)
        for finding in findings.findings:
            target = (f"第{finding.sentence}句" if finding.sentence
                      else finding.rule_id)
            report.add(Signal(
                rule=finding.rule_id,
                layer=TEXT_LAYER,
                severity=ERROR if finding.level == persona.ERROR else WARN,
                target=target,
                excerpt="",
                detail=finding.message,
            ))
        report.note(f"人格检查：{len(findings.sentences)} 句，"
                    f"{len(findings.errors)} 个硬约束违规，"
                    f"{len(findings.warnings)} 个倾向未达标")
    except (OSError, ValueError) as exc:
        report.note(f"人格检查没跑起来：{exc}")
    return report


# ---------------------------------------------------------------- 成片层


def load_media(episode: str) -> Media:
    """装齐成片层的输入。产物不在就记 note，不静默跳过。"""
    notes: list[str] = []
    video = AIV_ROOT / "out" / f"{episode}.mp4"
    if not video.is_file():
        notes.append(f"成片不在本机（{video}）：成片层整体跳过")
        video = None

    storyboard: Storyboard | None = None
    storyboard_path = episodes.storyboard_path(episode)
    if storyboard_path.is_file():
        try:
            storyboard = Storyboard.load(storyboard_path)
        except (OSError, KeyError, ValueError) as exc:
            notes.append(f"时间轴读不出来（{exc}）：VV-04 跳过")
    else:
        notes.append(f"时间轴不在本机（{storyboard_path}）："
                     "VV-04、VV-05 与混音区间检查跳过")

    narration = episodes.narration_path(episode)
    if not narration.is_file():
        notes.append(f"旁白不在本机（{narration}）：VV-03 跳过")
        narration = None

    bgm = AIV_ROOT / "music" / "tracks" / "series-bed-01.wav"
    if not bgm.is_file():
        notes.append(f"BGM 母带不在本机（{bgm}）：VV-06 跳过")
        bgm = None

    return Media(episode=episode, video=video, storyboard=storyboard,
                 narration=narration, bgm=bgm, notes=notes)


def _keyframe_times(video: Path) -> list[float]:
    result = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
        "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(video),
    ])
    if result is None or result[0] != 0:
        return []
    times = []
    for line in result[1].splitlines():
        line = line.strip().rstrip(",")
        if not line or line == "N/A":
            continue
        try:
            times.append(float(line))
        except ValueError:
            continue
    times.sort()
    return times


def _scene_spans(storyboard: Storyboard) -> list[tuple[Scene, float, float]]:
    """每一段在成片里的**真实**区间（秒），按帧算。

    时间轴上的段边界是浮点秒，成片却是按帧拼起来的：`render.py` 每段
    渲染 `round(duration * fps)` 帧，`compose.py` 按顺序拼片段。所以成片里
    真实的段边界与名义值差最多一帧（24fps 下 42 ms），且逐段累积。

    **这半帧的偏差会咬人**：编码器切出来的关键帧常常正好落在真实边界上。
    实测 parallel-apply：名义 s01→s02 在 5.977 s，真实切点在 5.958 s，
    而关键帧就在 5.958 s。按名义秒归属，这一帧画面上已经是下一段、
    归属却记成上一段——抽帧清单就会拿「下一段的画面」去核对「上一段的
    文案」，一整片假漏字。

    品牌片是同一套：素材片本身 68 帧（24fps），名义时长 2.833 s，
    `round(2.833 * 24)` 正好 68，对得上。
    """
    fps = storyboard.video.fps
    spans: list[tuple[Scene, float, float]] = []
    frame = 0
    for scene in storyboard.scenes:
        count = max(1, int(round(scene.duration * fps)))
        spans.append((scene, frame / fps, (frame + count) / fps))
        frame += count
    return spans


def _scene_at(storyboard: Storyboard | None, t: float) -> str:
    """这个时间码属于哪一段。

    **按成片的真实边界归属，不按时间轴上的名义秒。** 见 `_scene_spans`：
    名义边界与成片里的切点差最多一帧，关键帧又常常正好落在切点上，
    按名义值判就会把「下一段的画面」记成上一段。

    **边界归后一段。** 落在端点上的那一帧，画面上已经是后一段了
    （它就是后一段的第一帧）。所以取**起始时间不大于 t 的最后一段**。
    """
    if storyboard is None:
        return ""
    current = ""
    for scene, start, _end in _scene_spans(storyboard):
        if start <= t:
            current = scene.id
        else:
            break
    return current


def _flatten_strings(value) -> list[str]:
    """把 params 里（可能嵌着列表的）字符串值按顺序摊平。

    契约里的文案不只在顶层：`s03.modes` 是 `[["KEY SHARE", "FOR KEY SHARE"], …]`，
    `s05.bit_labels` 同理。只取顶层字符串，出来的清单会漏掉一半以上
    该有的字——「字对不对」这一问就无从回答。
    """
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        values: list[str] = []
        for item in value:
            values.extend(_flatten_strings(item))
        return values
    return []


def _expected_text(segments: list[contract_mod.Segment], scene_id: str) -> str:
    """这段**应该**出现什么文案：从契约的 params 抽所有字符串值（含嵌套）。"""
    for segment in segments:
        if segment.id != scene_id:
            continue
        values: list[str] = []
        for value in segment.params.values():
            values.extend(_flatten_strings(value))
        return " / ".join(values)
    return ""


def _snap_to_frame(t: float, fps: int) -> float:
    """把时间码吸附到帧网格上。

    ffprobe 报关键帧时间只到 6 位小数（`5.958333`），比真正的帧边界
    （143/24 = 5.9583333…）差在最后一位上。拿未吸附的时间去归属，
    「正好落在段边界上的关键帧」就会被判给上一段——而它其实是下一段
    的第一帧，画面上已经切过去了。
    """
    return round(t * fps) / fps


def extract_frames(media: Media, out_dir: Path,
                   materials: Materials | None = None,
                   keyframe_limit: int = 12) -> list[Frame]:
    """抽帧：每个视觉段 2 帧（段中点 + 段尾）+ 关键帧。

    抽帧是**稀疏**的：逐帧扫描在完整版（2.6 万帧）上不可行。
    段中点是最可能「画面已画完、字幕已烧上」的时刻，
    段尾帧补上「结论还在淡入」的时段（见 `SCENE_FRAME_POINTS`），
    关键帧往往正好落在段边界——段边界最容易出错。

    **所有时间码都吸附到帧网格**：归属要按成片里的真实切点算（见
    `_scene_spans`），而 ffprobe 给的关键帧时间差最后一位小数就会判错段。
    """
    if media.video is None or not media.video.is_file():
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Frame] = []
    index = 0

    segments = materials.segments if materials else []
    storyboard = media.storyboard
    fps = storyboard.video.fps if storyboard is not None else 0
    if storyboard is not None:
        for scene, start, end in _scene_spans(storyboard):
            if scene.type != "code" or scene.duration <= 0:
                continue
            for label, ratio in SCENE_FRAME_POINTS:
                # 用成片里的真实区间取帧：名义秒与真实切点差最多一帧，
                # 按名义秒抽出来的「段中点」可能落在上一段的尾巴上。
                t = _snap_to_frame(start + (end - start) * ratio, fps)
                index += 1
                path = out_dir / f"{index:02d}_{scene.id}_{label}.png"
                if _grab(media.video, t, path):
                    frames.append(Frame(
                        index=index, time=t, scene_id=scene.id, path=path,
                        kind="scene" if label == "mid" else "late",
                        subtitle=_subtitle_at(storyboard, t),
                        expected=_expected_text(segments, scene.id),
                    ))

    for t in _keyframe_times(media.video)[:keyframe_limit]:
        if fps:
            t = _snap_to_frame(t, fps)
        index += 1
        path = out_dir / f"{index:02d}_key_{t:.3f}.png"
        if _grab(media.video, t, path):
            frames.append(Frame(
                index=index, time=t, scene_id=_scene_at(storyboard, t),
                path=path, kind="keyframe",
                subtitle=_subtitle_at(storyboard, t) if storyboard else "",
            ))
    return frames


def _subtitle_at(storyboard: Storyboard | None, t: float) -> str:
    if storyboard is None:
        return ""
    for event in storyboard.subtitle_events():
        if event.start <= t <= event.end:
            return event.text
    return ""


def _grab(video: Path, t: float, out: Path) -> bool:
    result = _run([
        "ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
        "-frames:v", "1", "-f", "image2", str(out),
    ])
    return result is not None and result[0] == 0 and out.is_file()


def _frame_pixels(path: Path):
    from PIL import Image  # 延迟导入：doctor 才检查 PIL

    with Image.open(path) as image:
        return image.convert("RGB")


def vv_01_blank_frames(frames: list[Frame],
                      notes: list[str] | None = None) -> list[Signal]:
    """抽到的帧近乎纯色 → 画面漏画或黑场。"""
    from PIL import ImageStat

    hits = []
    for frame in frames:
        try:
            image = _frame_pixels(frame.path)
        except Exception as exc:  # noqa: BLE001 - 读不出图也是信号
            hits.append((frame, f"读不出像素：{exc}"))
            continue
        stat = ImageStat.Stat(image)
        deviation = sum(stat.stddev) / 3
        if deviation < BLANK_FRAME_STDDEV:
            hits.append((frame, f"像素标准差 {deviation:.2f}（近乎纯色）"))
    if not hits:
        return []
    detail = (f"{len(hits)} 帧近乎纯色："
              + "、".join(f"{frame.index}@{frame.time:.2f}s {why}"
                         for frame, why in hits[:8]))
    return [Signal("VV-01", VIDEO_LAYER, WARN,
                   f"第{hits[0][0].index}帧 {hits[0][0].time:.2f}s",
                   hits[0][0].scene_id, detail)]


def vv_02_missing_subtitle(frames: list[Frame],
                           notes: list[str] | None = None) -> list[Signal]:
    """帧的底部字幕带里没有暗色像素 → 字幕可能没烧上。

    **判据**：字幕是深蓝字（`#1B2A47`）配白描边，落在白色背景上；
    有字幕就有暗像素，没有就没有。
    画面底部本来就有深色内容时会**漏报**（假阴性）——宁可漏报不误报。
    """
    hits = []
    for frame in frames:
        if not frame.subtitle:
            continue
        try:
            image = _frame_pixels(frame.path)
        except Exception as exc:  # noqa: BLE001
            _note(notes, f"第{frame.index}帧的像素读不出来（{exc}）：VV-02 少判一帧")
            continue
        width, height = image.size
        band_top = int(height * (1 - SUBTITLE_BAND_RATIO))
        band = image.crop((0, band_top, width, height)).convert("L")
        histogram = band.histogram()
        dark = sum(histogram[:SUBTITLE_DARK_LUMA])
        total = band.size[0] * band.size[1]
        ratio = dark / total if total else 0.0
        if ratio < SUBTITLE_DARK_RATIO:
            hits.append((frame, ratio))
    if not hits:
        return []
    detail = (f"{len(hits)} 帧的字幕带里没有暗色像素（字幕可能没烧上）："
              + "、".join(f"{frame.index}@{frame.time:.2f}s「{frame.subtitle[:12]}」"
                         for frame, _ in hits[:8]))
    return [Signal("VV-02", VIDEO_LAYER, WARN,
                   f"第{hits[0][0].index}帧 {hits[0][0].time:.2f}s",
                   hits[0][0].subtitle[:40], detail)]


def _note(notes: list[str] | None, text: str) -> None:
    """记一条「这条规则没跑成」的原因。

    **规则跑不动的时候必须说话。** 静默返回空列表和「查了没问题」
    在报告里长得一模一样——混起来就成了假装绿。
    """
    if notes is not None:
        notes.append(text)


def vv_03_narration_silence(media: Media, notes: list[str] | None = None) -> list[Signal]:
    """正文区间里旁白中间静音。

    查的是**旁白文件**而不是成片混音：成片有 BGM 铺底，
    混音里根本听不出断句。旁白是纯的，断句才看得见。

    **只看句与句之间的空档**：开头与结尾的静音是录音的边，
    不是断句，报出来是噪声。
    """
    if media.narration is None:
        return []
    try:
        spans = align.detect_sentences(media.narration)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        _note(notes, f"旁白断句读不出来（{exc}）：VV-03 跳过")
        return []
    gaps = []
    for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
        if next_start - prev_end >= NARRATION_SILENCE_S:
            gaps.append((prev_end, next_start))
    if not gaps:
        return []
    detail = (f"{len(gaps)} 处旁白静音超过 {NARRATION_SILENCE_S}s："
              + "、".join(f"{start:.2f}~{end:.2f}s" for start, end in gaps[:8]))
    return [Signal("VV-03", VIDEO_LAYER, WARN,
                   f"{gaps[0][0]:.2f}s", "", detail)]


def vv_04_duration(media: Media, notes: list[str] | None = None) -> list[Signal]:
    """成片时长与时间轴对不上。"""
    if media.video is None or media.storyboard is None:
        return []
    duration = _probe_duration(media.video)
    if duration is None:
        _note(notes, "成片时长读不出来（ffprobe 没装或读不了这个文件）：VV-04 跳过")
        return []
    expected = media.storyboard.duration
    if abs(duration - expected) <= DURATION_TOLERANCE_S:
        return []
    detail = (f"成片 {duration:.3f}s，时间轴 {expected:.3f}s，"
              f"差 {duration - expected:+.3f}s（容差 {DURATION_TOLERANCE_S}s）")
    return [Signal("VV-04", VIDEO_LAYER, ERROR, f"{duration:.3f}s", "", detail)]


def vv_05_keyframes(media: Media, notes: list[str] | None = None) -> list[Signal]:
    """关键帧最大间隔。"""
    if media.video is None:
        return []
    from pyv import preflight

    try:
        gaps = preflight.keyframe_gaps(media.video)
    except (RuntimeError, OSError) as exc:
        _note(notes, f"关键帧读不出来（{exc}）：VV-05 跳过")
        return []
    if not gaps:
        _note(notes, "一个关键帧都没读到：VV-05 跳过（成片可能没有视频轨）")
        return []
    worst = max(gaps)
    if worst <= MAX_KEYFRAME_GAP_S:
        return []
    detail = (f"关键帧最大间隔 {worst:.3f}s，超过 {MAX_KEYFRAME_GAP_S}s。"
              f"修复：ffmpeg -i <成片> -c:v libx264 -preset medium -crf 18 -g 240 "
              f"-c:a aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart <输出>")
    return [Signal("VV-05", VIDEO_LAYER, WARN, f"{worst:.3f}s", "", detail)]


def vv_06_mix(media: Media, notes: list[str] | None = None) -> list[Signal]:
    """混音电平。判定直接调 `bgm.py`，不重写。"""
    if media.video is None or media.narration is None or media.bgm is None:
        return []
    if media.storyboard is None:
        return []
    from pyv import bgm as bgm_rules
    from pyv import compose

    try:
        body_start, body_end = compose._body_range(media.storyboard)
        report = bgm_rules.measure_mix(media.video, media.narration, media.bgm,
                                        body_start, body_end)
        findings = bgm_rules.check_mix(report)
    except (OSError, RuntimeError, ValueError) as exc:
        _note(notes, f"混音量不出来（{exc}）：VV-06 跳过")
        return []
    hits = [f for f in findings if f.level == bgm_rules.ERROR]
    if not hits:
        return []
    detail = "；".join(str(f) for f in hits[:6])
    return [Signal("VV-06", VIDEO_LAYER, WARN, "混音", "", detail)]


def vv_07_platform(media: Media, notes: list[str] | None = None) -> list[Signal]:
    """平台技术门槛。判定直接调 `preflight.py`，平台清单只有一个来源。"""
    if media.video is None:
        return []
    from pyv import epmeta, preflight

    try:
        info = preflight.probe(media.video)
    except (RuntimeError, OSError, FileNotFoundError) as exc:
        _note(notes, f"成片参数读不出来（{exc}）：VV-07 跳过")
        return []
    hits = []
    for platform in epmeta.PLATFORM_SPECS:
        try:
            findings = preflight.check_video(info, platform)
        except (OSError, ValueError) as exc:
            _note(notes, f"平台 {platform} 的门槛读不出来（{exc}）：VV-07 少判一个平台")
            continue
        for finding in findings:
            if finding.level == preflight.ERROR:
                hits.append((platform, finding))
    if not hits:
        return []
    detail = "；".join(f"[{platform}] {finding.message}"
                       for platform, finding in hits[:6])
    return [Signal("VV-07", VIDEO_LAYER, ERROR, hits[0][0], "", detail)]


VIDEO_CHECKS = (
    vv_01_blank_frames,
    vv_02_missing_subtitle,
)


def _is_brand_frame(frame: Frame,
                    storyboard: Storyboard | None = None) -> bool:
    """这一帧落在品牌片头/片尾里。

    品牌片是**共享素材**（`aiv/brand/clips/` 下的固定片子），不是这一期
    渲染出来的。片头第一帧是黑场（淡入），那是设计，不是漏画——
    拿 VV-01 去判它，每期都会报一条假警。

    **边界帧也算品牌片**：品牌片片尾是淡出到白场的，最后几十毫秒是纯白帧；
    编码器切出来的关键帧常正好落在「品牌片结束、正文段开始」的那一帧，
    它在时间轴上属于正文段，实际上是品牌片的淡出。
    实测 ep01：品牌片 2.833 s 结束，2.79 s 之后已是纯白，
    而落在 2.8333 s 的关键帧被算进了 s01，VV-01 报了一条假警。
    所以边界给半帧多的容差（24fps 一帧约 0.042 s）。
    """
    if frame.scene_id.startswith("brand"):
        return True
    if storyboard is None:
        return False
    for scene, start, end in _scene_spans(storyboard):
        if not scene.id.startswith("brand"):
            continue
        if (abs(frame.time - start) <= BRAND_EDGE_TOLERANCE_S
                or abs(frame.time - end) <= BRAND_EDGE_TOLERANCE_S):
            return True
    return False


def check_video(episode: str, out_dir: Path | None = None) -> Report:
    """跑成片层。

    需要本机的成片与时间轴。产物不在时，note 说清跳过了什么。
    """
    media = load_media(episode)
    report = Report(episode=episode, layer=VIDEO_LAYER)
    for note in media.notes:
        report.note(note)
    if media.video is None:
        return report

    target_dir = out_dir or (FRAMES_DIR / episode)
    materials = load_materials(episode)
    frames = extract_frames(media, target_dir, materials=materials)
    if frames:
        manifest = write_frame_manifest(frames, target_dir, materials)
        report.note(f"抽了 {len(frames)} 帧 → {target_dir}；清单 → {manifest}")
    else:
        report.note("没抽到帧：VV-01、VV-02 跳过")

    body_frames = [frame for frame in frames
                   if not _is_brand_frame(frame, media.storyboard)]
    skipped = len(frames) - len(body_frames)
    if skipped:
        report.note(f"{skipped} 帧在品牌片头/片尾里或紧邻其边界（过渡帧），"
                    "不判 VV-01、VV-02"
                    "（品牌片是共享素材：片头第一帧的黑场、"
                    "片尾最后几十毫秒的白场都是淡入淡出；"
                    "边界那一帧可能落在正文段刚起的空白上——都不是漏画）")

    for check in VIDEO_CHECKS:
        skipped: list[str] = []
        for signal in check(body_frames, skipped):
            report.add(signal)
        for text in skipped:
            report.note(text)

    for check in (vv_03_narration_silence, vv_04_duration, vv_05_keyframes,
                  vv_06_mix, vv_07_platform):
        skipped: list[str] = []
        for signal in check(media, skipped):
            report.add(signal)
        for text in skipped:
            report.note(text)
    return report


# ---------------------------------------------------------------- 抽帧清单

#: 清单里的类型名：给人看的，不是给代码看的。
KIND_LABELS = {"scene": "段中点", "late": "段尾", "keyframe": "关键帧"}


def build_frame_manifest(frames: list[Frame],
                         materials: Materials | None = None) -> str:
    """抽帧清单：给人看的对照表。

    「这段应该出现什么」来自**契约的 params**——那是画面上真正要写的字，
    也是判断「画面画对没有」的对照物。
    """
    segments = materials.segments if materials else []
    lines = [
        "# 抽帧清单",
        "",
        "每一帧对着三件事看：**画面上有没有该有的字**、**字对不对**、"
        "**这一帧讲不讲得清**。",
        "",
        "**段中点**是画面画得最完整的时刻，**段尾**是结论淡入完之后的样子"
        "（只看段中点会把动画中间态当成漏字）。",
        "",
        "| 帧 | 类型 | 时间码 | 视觉段 | 应有文案 | 口播 | 文件 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for frame in frames:
        expected = frame.expected or _expected_text(segments, frame.scene_id)
        lines.append(
            f"| {frame.index} | {KIND_LABELS.get(frame.kind, frame.kind)} | "
            f"{frame.time:.3f}s | "
            f"{frame.scene_id or '—'} | {expected or '—'} | "
            f"{frame.subtitle or '—'} | `{frame.path.name}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_frame_manifest(frames: list[Frame], out_dir: Path,
                         materials: Materials | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "frames.md"
    target.write_text(build_frame_manifest(frames, materials), encoding="utf-8")
    return target


def extract_and_manifest(episode: str, out_dir: Path) -> tuple[list[Frame], Path | None]:
    """抽帧 + 写清单。成片不在本机时返回空清单，不假装抽过。"""
    media = load_media(episode)
    if media.video is None:
        return [], None
    materials = load_materials(episode)
    frames = extract_frames(media, out_dir, materials=materials)
    return frames, write_frame_manifest(frames, out_dir, materials)


# ---------------------------------------------------------------- CLI 支撑


def report_json(report: Report) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def check_episode(episode: str) -> dict:
    """两层一起跑，给进度表用。"""
    text = check_text(episode)
    video = check_video(episode)
    return {
        "episode": episode,
        "text": text.to_dict(),
        "video": video.to_dict(),
    }
