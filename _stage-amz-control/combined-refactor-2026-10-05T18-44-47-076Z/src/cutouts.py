r"""素材抠图产出一份 —— 位置 6/7 的「内容物 / 竞品」在这里抠，不在渲染器里抠。

它解决的是什么
--------------
    在 M5 里，`contents_compose` 与 `compare_side` 各自在用的时候抠自己的素材。
    那样有三个问题，其中第一个是**实测撞出来的**：

      1. **顺序** —— 抠图推理会偶发抓不到内存（ORT `bad allocation` /
         numpy `MemoryError`）。同一个调用，进程刚起来时稳；跑完一次 55s 的云端
         生成之后就不稳了。而位置 6/7 恰好排在位置 4 后面，于是"整格失败"。
         把三处抠图都提到模型调用**之前**，它们就都发生在进程最清爽的时候。
      2. **不烧冤枉钱** —— 抠图失败就不该再去调模型。这条规矩本来就在主体那一步
         写着（见 orchestrator.execute 的注释），只是当时只管了主体。
      3. **一轮只抠一次** —— 抠完的素材在本轮里不该再变。否则
         `--redo 7 --layer placement`（只挪一下位置）会重抠竞品，
         既多花 25s，又可能因为"这次抠图走了另一条路"而**换掉像素** ——
         "只改了位置"这句话就不成立了。

归属（分清，否则会长出第二个真相源）
----------------------------------
    src/subject.py   **我们的主体**只有一份（不变量 A）—— 5 个坑位共用 subject.png
    src/cutouts.py   每个**外来素材**各抠一份（内容物 / 竞品）—— 各有一个消费者
    src/synth.py     抠图这件事本身（判据、降级规则、耗时口径）

    两者的**判据与反应相同**（`synth.cutout_is_suspect` 一处定义），
    差别只在"错了会怎样"：主体错了七张图全错（整批停），
    内容物错了那一格没法做（跳过那一格，别的照出）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

import synth

# 抠好的素材落在 raw/ 下 —— 与"文字底 / 生成底"同一个地方。
# raw/ 的定义就是"可重做的物质基础"，抠好的素材正是其中之一：
# 重做位置 6/7 时直接读它，不重抠。
RAW_DIR = "raw"


def name_of(kind: str) -> str:
    return f"cut_{kind}.png"


def path_of(run_dir: str | Path, kind: str) -> Path:
    return Path(run_dir) / RAW_DIR / name_of(kind)


def prepare(kind: str, src_path: str | Path, run_dir: str | Path, *,
            cutout_mode: str | None = None) -> dict:
    """抠一样素材并落盘，返回它的描述（与 subject.prepare 同形状）。

    调用方（orchestrator）负责决定**什么时候**调它 —— 本模块不读盘找素材、
    也不判断该不该抠，只做"把这一张变成抠好的那一张"。
    """
    src_path, run_dir = Path(src_path), Path(run_dir)
    img = Image.open(src_path)
    img.load()                        # 真解码一次：截断文件在此现形

    rgba, cut_info = synth.remove_background(img, mode=cutout_mode)
    bbox = synth.alpha_bbox(rgba)
    if bbox is None:
        raise ValueError(
            f"{kind} 素材里没有分离出任何前景：{src_path.name} —— "
            f"抠图把整张图都当成了背景。可行修法：① 换对比明显的背景重拍；"
            f"② 直接提供已抠好的透明 PNG")

    tight = rgba.crop(bbox)
    coverage = synth.alpha_coverage(tight)

    # 判据与主体**同一套**（synth.cutout_is_suspect 一处定义），
    # 反应是这里的：抠穿了就没法用 —— 白底/边缘类校验会假通过，
    # 而且这一格本来画的就是**事实**（盒子里有什么、竞品长什么样），
    # 拿一张抠穿的图去讲事实，比不出图更坏。
    reason = synth.cutout_is_suspect(cut_info, coverage)
    if reason:
        raise ValueError(f"{kind} 素材 {src_path.name}：{reason}")

    out = path_of(run_dir, kind)
    out.parent.mkdir(parents=True, exist_ok=True)
    tight.save(out, "PNG")

    return {
        "kind": kind,
        "path": str(out),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "size": [tight.width, tight.height],
        "source": str(src_path),
        "bbox_in_source": list(bbox),
        "cutout": cut_info,
        "alpha_coverage": round(coverage, 4),
    }
