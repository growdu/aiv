"""封面：抽一帧，再出后台要的两张槽位图。

**抖音创作者后台的封面槽位有两个**（2026-11-15 实测 creator.douyin.com）：
竖封面 **3:4** 与横封面 **4:3**。后台自己的「发文助手」在只给一张时会提示
「横/竖双封面缺失」——两张都要。

这两个比例是后台标在槽位上的，**不是猜的**。上一版写着「封面比例不猜，
先给与成片同比例的图，投完一条看后台实际怎么裁再定」——现在投过了，
答案就是后台写在那儿的两个比例。

出三张图，各有各的用处：

| 文件 | 比例 | 填哪 | 做法 |
| --- | --- | --- | --- |
| `cover.jpg` | 与成片同比例 | 不直接填槽位 | 原帧，不缩放不裁 |
| `cover_3x4.jpg` | 3:4 | 竖封面槽位 | 居中裁切 |
| `cover_4x3.jpg` | 4:3 | 横封面槽位 | 等比缩放居中，四周留白 |

**横封面为什么是留白而不是裁。** 竖版成片（9:16）裁一刀取 4:3，只剩
中间一条横带，画面里的字会被拦腰截断；留白保住整幅画面，代价是两侧
有底色——那本来就是给横版视频准备的槽位，竖片填它只能这样。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

#: 竖封面槽位（3:4）。
VERTICAL_COVER_SIZE = (1080, 1440)
#: 横封面槽位（4:3）。
HORIZONTAL_COVER_SIZE = (1200, 900)


def extract_frame(video: str | Path, at: float, out_path: str | Path) -> Path:
    """抽出某一时刻的一帧。"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([
        "ffmpeg", "-y", "-ss", f"{at:.3f}", "-i", str(video),
        "-frames:v", "1", str(out),
    ], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"抽帧失败：{(proc.stderr or '')[-400:]}")
    if not out.is_file():
        # ffmpeg 定位到成片末尾之后会「成功」但一个画面也不输出。
        # 那时候它退出码是 0，不检查文件的话就会把一个不存在的路径交给下一步。
        raise RuntimeError(
            f"抽帧失败：{at:.3f}s 处没有画面（取帧点超出成片时长？）")
    return out


def _crop_to_ratio(picture: Image.Image, ratio: tuple[int, int]) -> Image.Image:
    """居中裁到目标宽高比。"""
    width, height = picture.size
    target = ratio[0] / ratio[1]
    if width / height > target:
        new_width = max(1, int(round(height * target)))
        left = (width - new_width) // 2
        return picture.crop((left, 0, left + new_width, height))
    new_height = max(1, int(round(width / target)))
    top = (height - new_height) // 2
    return picture.crop((0, top, width, top + new_height))


def _contain_on_canvas(picture: Image.Image, size: tuple[int, int],
                       background: tuple[int, int, int] = (255, 255, 255),
                       ) -> Image.Image:
    """等比缩放居中放到画布上（留白）。"""
    canvas = Image.new("RGB", size, background)
    scale = min(size[0] / picture.width, size[1] / picture.height)
    resized = picture.resize(
        (max(1, int(picture.width * scale)),
         max(1, int(picture.height * scale))),
        Image.LANCZOS)
    canvas.paste(resized, ((size[0] - resized.width) // 2,
                           (size[1] - resized.height) // 2))
    return canvas


def make_covers(video: str | Path, at: float, out_dir: str | Path) -> dict:
    """抽一帧，出三张封面。

    返回 ``{"original": 路径, "vertical": 路径, "horizontal": 路径}``。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = extract_frame(video, at, out_dir / "_frame.png")

    paths = {
        "original": out_dir / "cover.jpg",
        "vertical": out_dir / "cover_3x4.jpg",
        "horizontal": out_dir / "cover_4x3.jpg",
    }
    with Image.open(raw) as frame:
        picture = frame.convert("RGB")
        picture.save(paths["original"], quality=92)
        _crop_to_ratio(picture, (3, 4)).resize(
            VERTICAL_COVER_SIZE, Image.LANCZOS).save(
                paths["vertical"], quality=92)
        _contain_on_canvas(picture, HORIZONTAL_COVER_SIZE).save(
            paths["horizontal"], quality=92)
    raw.unlink(missing_ok=True)
    return paths


def make_cover(video: str | Path, at: float, out_dir: str | Path) -> Path:
    """抽一帧，存成 `cover.jpg`（与成片同比例）。

    保留这个入口是为了不打断别的调用方；后台槽位那两张用 `make_covers`。
    """
    return make_covers(video, at, out_dir)["original"]
