r"""主体只有一份 —— 不变量 A 的落地位置。

它解决的不是"省一次抠图"
------------------------
    七张图共用同一个商品主体，这是**数据约束**，不是提示词期望。
    若让每个渲染器自己去抠 `front`，系统里就会出现七个"主体"：

      · 每次抠图都是一次独立推断，边缘像素不保证一致；
      · 位置 1 与位置 2 的主体轮廓不同 → 成套图看起来不像同一个东西；
      · 抠图失败会在七个地方分别发生，日志里要读七条才知道出了什么事。

    所以本模块是主体**唯一的生产者**：一轮 run 产出一张 `subject.png`，
    之后所有需要主体的渲染器都读它（`ctx["subject"]`）。
    `renderers/compose_white.py` 与 `renderers/flat_overlay.py` 里
    **没有抠图调用** —— 这就是那条不变量的代码级证据。

它属于哪一类（分清归属，否则会长成第二个真相源）
----------------------------------------------
    src/assets.py    齐套判定 —— 这次做哪几张
    src/intake.py    E0 体检 —— 这张原片能不能用
    src/subject.py   主体产出一份 —— **把能用的原片变成共用的主体资产**（本模块）

输入用的是 E0 已经验过的 `front`。于是"抠完才发现图是坏的"不可能发生：
坏图在 E0 就被拒了，走不到这里。

零 API 成本
-----------
    抠图走的是**本地** BiRefNet-lite（见 synth.remove_background 的降级链），
    不联网、不下载、不计入"模型调用次数"。registry 里的 `calls_model`
    指的是云端生成模型（位置 4 那一格），两者不是一回事。
"""
from __future__ import annotations

import gc
import hashlib
from pathlib import Path

from PIL import Image

import intake
import synth

SUBJECT_NAME = "subject.png"

# 抠图有效性的阈值与判据**不在这里** —— 它是"抠图"这件事的性质，不是"主体"的性质。
# 定义在 synth.SUSPECT_ALPHA_COVERAGE / synth.cutout_is_suspect（一处定义，
# subject / contents_compose / compare_side 三个消费方，各自反应不同、判据相同）。
# 这里只保留一条口径说明：覆盖率必须在**紧缩之后**的 alpha 上量。


class SubjectError(Exception):
    """主体产不出来 —— 属**输入问题**（工具修不了），必须给出可执行的下一步。"""


def needs_subject(slots: list[dict]) -> bool:
    """本次要跑的坑位里，有没有需要主体的。

    判据是 `needs` 里有没有 `front` —— 主体由 front 派生，这是**唯一**的推导规则。
    刻意不写成配置项：多一个开关，就多一个能和 `needs` 打架的地方。
    """
    return any("front" in (s.get("needs") or []) for s in slots)


def prepare(front_path: str | Path, run_dir: str | Path, *,
            cutout_mode: str | None = None) -> dict:
    """产出本轮唯一的主体资产，返回它的描述。

    返回里带 `sha256` 与 `size`：验收断言"位置 1/2/3 的产品像素同源"
    靠的就是它们（见 tools/verify_m3.py），而不是目测。
    """
    front_path, run_dir = Path(front_path), Path(run_dir)
    img = Image.open(front_path)
    img.load()                       # 真解码一次：截断文件在此现形

    if intake.has_alpha(img):
        # 已经是一张抠好的图 → 直接采用，不再抠。
        # E0 在 M2 就为这种情况写过提醒（"已是抠好的图 …[M3 落地]"），
        # 这里是那个提醒的消费方；同时它也是抠图失败时**唯一的逃生通道**。
        rgba, cut_info = img.convert("RGBA"), {"mode": "existing_alpha"}
    else:
        try:
            rgba, cut_info = synth.remove_background(img, mode=cutout_mode)
        except synth.CutoutError as exc:
            # 抠图**推理**失败（环境瞬时故障，见 synth.CutoutError）和"输入没法抠"
            # 是两回事，但对本模块的后果一样：产不出主体。所以并成 SubjectError
            # 一起交出去 —— 上层只需要知道"这一步没成功"，以及**接下来怎么办**
            # （那句话在 exc 里，逐字保留，不要在这里改写成泛泛的失败）。
            raise SubjectError(str(exc)) from exc
        # ★ 显式回收一次（这不是"顺手加个 gc"，它修的是一个**日志说谎**的问题）：
        #   onnxruntime 的会话带着大块显存/内存且带引用环，靠 GC 回收；
        #   不在这里收，那次回收会落在**后面任意一个渲染步骤**上 ——
        #   实测日志出现过"位置 4 渲染耗时 17.1s"，而位置 4 当时只画了一个灰框。
        #   让成本落在产生它的那一步，耗时数据才可信。
        gc.collect()

    bbox = synth.alpha_bbox(rgba)
    if bbox is None:
        raise SubjectError(
            f"从 {front_path.name} 里没有分离出任何前景 —— 抠图把整张图都当成了背景。"
            f"可行修法：① 换对比明显的背景重拍；"
            f"② 直接提供已抠好的透明 PNG 作为 front。")

    tight = rgba.crop(bbox)          # 紧缩：subject.png 就是"主体本身"，不含多余画布
    coverage = synth.alpha_coverage(tight)

    # 抠图没生效 → 硬失败。判据在 synth（三个消费方共用），但**反应是本格的**：
    # 我们的主体错了，七张图都错，所以整批停下，而不是"记个提醒继续"。
    reason = synth.cutout_is_suspect(cut_info, coverage)
    if reason:
        raise SubjectError(
            f"{reason}。本例来源：{Path(front_path).name}")

    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / SUBJECT_NAME
    tight.save(out, "PNG")
    sha = hashlib.sha256(out.read_bytes()).hexdigest()

    return {
        "path": str(out),
        "sha256": sha,
        "size": [tight.width, tight.height],     # 紧缩后的主体尺寸（贴图时的源尺寸）
        "source": str(front_path),
        "bbox_in_source": list(bbox),
        "cutout": cut_info,
        "alpha_coverage": round(coverage, 4),
    }
