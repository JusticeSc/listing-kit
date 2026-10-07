"""位置 1（亚马逊主图）确定性合成链路。

为什么这一张不调用生成模型：
    纯白底 RGB(255,255,255) + 产品占比 >=85% + 无道具 + 禁文字，这是
    **确定性图像处理**问题。用生成模型做白底主图 = 用概率工具做确定性任务：
    它会加不存在的细节、会变形、会画假字，而这一张的容错是零
    （违规 = listing 降权 / 下架）。
    这条路不产生任何模型调用成本，且质量最稳定。

抠图的两条路：
    0. rembg（BiRefNet-general-lite）—— 质量最好，**模型已在本地**，不联网、不下载
    1. 四角洪水填充 —— 带连通性约束，零依赖；多色背景（木桌 + 墙面）也不会
       把整图判成前景（色差阈值法会，实测踩过）

为什么把模型路径写进来：
    rembg 找不到模型时会去 GitHub Releases 下载，国内网络实测读超时（30s），
    每次运行都白等一轮。所以这里改成**本地优先 + 找不到就不下载**：
    模型目录找不到时直接降级到洪水填充，并把原因写进日志。

★ 降级只允许发生在**确定的条件**上（详见 remove_background）：
    模型不在（配置事实：每次调用都一样）→ 降级
    推理失败（环境瞬时故障：这次炸、下次可能不炸）→ 重试，仍失败就报错

无论走哪条路，都会计算 alpha 前景覆盖率做**抠图有效性自检**（cutout_suspect）：
覆盖率接近整图 ⇒ 抠图没生效，此时四周留白是合成上去的白画布，
所有边缘类校验都会假通过，必须在 pipeline 里显式拦下来。
"""
from __future__ import annotations

import gc
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FILL_TOLERANCE = 0.02  # 占比允差

# Numba 默认先尝试在解释器的 site-packages 下写编译缓存，再退到用户缓存。
# 这两处在受控运行环境里都可能只读，结果不是“变慢”，而是 rembg 导入阶段直接
# 抛 `no locator available`。缓存属于本项目的可删除运行产物，因此默认放在项目
# 自己的 E 盘目录；显式 NUMBA_CACHE_DIR 始终优先，便于部署方统一管理。
os.environ.setdefault(
    "NUMBA_CACHE_DIR",
    str(Path(__file__).resolve().parent.parent / ".cache" / "numba"),
)

# ---------------------------------------------------------------- 抠图模型

# 会话名 → 对应 <模型目录>/<会话名>.onnx
# birefnet-general-lite = BiRefNet (swin tiny) 轻量版，边缘比 u2net 干净
DEFAULT_SESSION = "birefnet-general-lite"
FALLBACK_SESSIONS = ["birefnet-general-lite", "u2net"]

# 模型目录候选（按优先级）。放在 E 盘，避免占 C 盘。
MODEL_DIR_CANDIDATES = [
    os.getenv("REMBG_MODEL_DIR", ""),
    r"E:\model_repository\model_scope\rembg",
]


def resolve_model_dir() -> str | None:
    for p in MODEL_DIR_CANDIDATES:
        if p and os.path.isdir(p):
            return p
    return None


def _model_file(home: str, session: str) -> str | None:
    """rembg 的查找顺序：<home>/models/<name>/<name>.onnx → <home>/<name>.onnx。"""
    fname = f"{session}.onnx"
    for c in (os.path.join(home, "models", session, fname), os.path.join(home, fname)):
        if os.path.exists(c):
            return c
    return None


# 会话缓存。名字 → session 对象。
#
# ★ 为什么必须有：加载一次 BiRefNet 会话约 19s（实测）。M5 之后链路里有**三处**
#   需要抠图（主体 / 内容物 / 竞品），各自调一次 remove_background ——
#   不缓存就是 3×19s 白等，而且全都记在"渲染耗时"上，看起来像是渲染很慢。
#   "让成本落在产生它的那一步"这条纪律有个前提：那个成本本身不该是重复的。
_SESSION_CACHE: dict[str, object] = {}


def _load_session():
    """加载 rembg 会话。返回 (session, info)；本地无模型则 session=None 且**不下载**。"""
    home = resolve_model_dir() or os.getenv("U2NET_HOME") or ""
    if home:
        os.environ.setdefault("U2NET_HOME", home)

    try:
        from rembg import new_session  # type: ignore
    except Exception as exc:
        return None, {"error": f"rembg 不可用: {str(exc)[:100]}"}

    names = [os.getenv("REMBG_SESSION") or DEFAULT_SESSION]
    names += [s for s in FALLBACK_SESSIONS if s not in names]
    tried = []
    for name in names:
        path = _model_file(home, name) if home else None
        if not path:
            tried.append({"session": name, "reason": "本地无模型文件"})
            continue
        cached = _SESSION_CACHE.get(name)
        if cached is not None:
            return cached, {"session": name, "model_path": path, "home": home,
                            "cached": True}
        try:
            sess = new_session(name)
            _SESSION_CACHE[name] = sess
            return sess, {"session": name, "model_path": path, "home": home,
                          "cached": False}
        except Exception as exc:
            tried.append({"session": name, "reason": str(exc)[:120]})
    return None, {"home": home, "tried": tried}


# ---------------------------------------------------------------- 抠图

# rembg **推理**的重试次数（含首次）。
#
# ★ 为什么需要它：实测推理会偶发抛
#       [ONNXRuntimeError] : 1 : FAIL : bad allocation
#   紧接着重试同一张图就能成功（同进程、同参数、同样内存压力下）。
#   这是环境瞬时的，不是输入的问题 —— 重试正是对症的处置。
INFER_ATTEMPTS = 3


class CutoutError(RuntimeError):
    """抠图**推理**失败：模型在本地、会话也建起来了，但调用炸了。

    它和"模型不在"必须分开处置，因为两者的**确定性**不同：

        模型不在   配置事实 → 这一轮每次调用都不在 → 降级 floodfill 是确定的
        推理失败   环境瞬时 → 这次炸下次可能不炸 → **绝不能**静默降级

    静默降级换掉的是像素，而版本对比的全部意义是"差异只来自被改的那一处"。
    """


def _drop_session(name: str | None) -> None:
    """丢掉缓存的会话 —— 推理失败后的重试要用它（见下）。

    会话是 onnxruntime arena 的宿主，而 arena 是进程里**最大的一块**可回收内存。
    失败（bad allocation / numpy MemoryError）说明进程已经拿不到内存了，
    这时候把会话丢掉 = 把那块内存还回去，重试才有意义。
    """
    if name and _SESSION_CACHE.pop(name, None) is not None:
        gc.collect()


def background_mask(img: Image.Image, tolerance: int = 70) -> "np.ndarray":
    """四角洪水填充 → 布尔背景蒙版（True = 与画面边缘连通的背景像素）。

    ★ 一处定义，两个消费方（所以它必须是公开纯函数，不是私有实现细节）：
        _cutout_by_floodfill    —— 取反得到前景 alpha
        fixers.fix_background   —— 把背景刷成纯白（**只刷背景，不碰主体**）

    第二个消费方是重构时加的：白底偏灰是最常见的失败形态，而"刷白"必须
    只刷背景。为什么不能用"亮度阈值"代替它：主体里同样有偏亮的像素
    （白瓷杯的高光、不锈钢反光），按亮度刷会把主体一起吃掉。
    **连通性约束**才是"哪些像素是背景"的正确判据。
    """
    work = img.convert("RGB").copy()
    w, h = work.size
    magic = (255, 0, 255)  # 照片里不会出现的哨兵色
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        try:
            ImageDraw.floodfill(work, seed, magic, thresh=tolerance)
        except Exception:
            pass
    arr = np.asarray(work)
    if arr.ndim != 3:
        return np.zeros(arr.shape, dtype=bool)
    return np.all(arr == np.array(magic, dtype=arr.dtype), axis=2)


def _cutout_by_floodfill(img: Image.Image, tolerance: int = 70):
    """从四角洪水填充背景 → 取反得到前景 alpha。

    比"四角色差阈值"稳的地方：洪水填充带**连通性约束**。
    实测教训：色差阈值法在"木桌 + 墙面"这类多色背景下会把整张图判成前景
    （背景颜色不统一，总有像素离四角色距 > 阈值），结果 bbox = 全图，
    产品区里全是原背景，而四周留白却是合成上去的白画布 —— 导致所有边缘类
    校验**假通过**。这也是 synth 里必须做 cutout_suspect 自检的原因。
    """
    is_bg = background_mask(img, tolerance)
    mask = np.where(is_bg, 0, 255).astype(np.uint8)
    m = Image.fromarray(mask, "L")
    m = m.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))  # 开运算去噪点
    m = m.filter(ImageFilter.GaussianBlur(0.8))
    out = img.convert("RGBA")
    out.putalpha(m)
    return out, {"mode": "floodfill", "tolerance": tolerance,
                 "bg_ratio": round(float(is_bg.mean()), 4)}


def remove_background(img: Image.Image, mode: str | None = None):
    """抠图。mode: auto | rembg | floodfill

    实测教训：rembg 找不到模型时会去 GitHub Releases 下载（约 170—214MB），
    国内网络经常读超时（30s）。所以这里改成**本地优先**：
      1. 先在 REMBG_MODEL_DIR（或 E:\\model_repository\\model_scope\\rembg）找 <会话名>.onnx
      2. 找不到 → 直接降级 floodfill，**绝不触发下载**，并把原因写进日志
      3. 会话加载失败 → 依次尝试 birefnet-general-lite / u2net，再不行降级

    降级判据：**只认"确定的条件"，不认"这次运气不好"**
    --------------------------------------------------
        rembg 不可用（未安装 / 本地无模型 / 会话加载失败）
            → 降级 floodfill。这是配置事实：同一轮 run 里每次调用结果一致，
              且原因写进 meta（rembg_skipped / rembg_tried）。

        rembg 可用但**推理失败**（bad allocation 之类）
            → 重试 INFER_ATTEMPTS 次；仍失败抛 CutoutError，**不静默降级**。

    ★ 第二种为什么不能降级（这是 M6 验收抓出来的真实缺陷，不是假设）
    ------------------------------------------------------------
        floodfill 抠出的 alpha 与 rembg 抠出的**相差十几万像素**。一旦静默换路，
        "重做一次"产出的图就与上一版不同 —— 而版本对比的全部意义正是
        "差异只来自被改的那一处"。实测记录：位置 7 重做时一次 bad allocation
        落到 floodfill，成品与上一版相差 184221 个像素（最大差 159），
        而日志里**没有任何"这一版换了抠图方法"的状态变化**；
        它只改变了像素，不改变任何可被读到的结论 —— 这就是"日志说谎"。

        想用 floodfill 就显式说：`--cutout floodfill` 或 CUTOUT_MODE=floodfill。
        显式选择是确定的（同一轮里每次都是 floodfill），猜出来的不是。
    """
    mode = (mode or os.getenv("CUTOUT_MODE") or "auto").lower()

    if mode == "floodfill":
        return _cutout_by_floodfill(img)

    session, info = _load_session()
    if session is None:
        rgba, meta = _cutout_by_floodfill(img)
        meta["rembg_skipped"] = "本地未找到模型文件，跳过 rembg（不触发下载）"
        if info.get("error"):
            meta["rembg_error"] = info["error"]
        if info.get("tried"):
            meta["rembg_tried"] = info["tried"]
        meta["model_dir"] = info.get("home") or ""
        return rgba, meta

    from rembg import remove as _rb_remove  # type: ignore

    failures: list[str] = []
    for attempt in range(1, INFER_ATTEMPTS + 1):
        try:
            out = _rb_remove(img.convert("RGBA"), session=session)
        except Exception as exc:  # noqa: BLE001  推理失败 → 重试（见 docstring）
            # ★ 必须把异常对象**放掉**再重试：它自己可能挂着一大段 traceback，
            #   而那正是"内存已经不够"时最不该继续占着的东西。
            failures.append(f"第 {attempt}/{INFER_ATTEMPTS} 次 "
                            f"{type(exc).__name__}: {str(exc)[:120]}")
            if attempt == INFER_ATTEMPTS:
                break
            # ★ 重试要**换一个会话**，而不是把同一个调用再念一遍。
            #   失败的原因是进程拿不到内存，而 ORT 的会话正握着它的 arena ——
            #   丢掉会话就等于把那块内存还回去。"重念一遍"只能等运气好转，
            #   清掉状态再试才是真正的重试。
            #
            # ★★ 顺序是这件事的**全部要点**（2026-09-21 复跑时抓出的真缺陷）：
            #     `session, info = _load_session()` 这种写法是错的 ——
            #     Python 会**先求完右边**（= 新建会话 = 立刻分配一块新 arena）
            #     再重新绑定左边的名字。也就是说旧会话在新建那一刻**仍然活着**，
            #     峰值内存直接翻倍。在"已经拿不到内存"的场景里，翻倍就是必输：
            #     实测注入一次偶发失败后，重试连续失败，日志里写着"连续失败 3 次"，
            #     看起来像"运气不好"，实际是自己制造的。
            #
            #     判据（探针 `_t_orderprobe.py`）：在 `_load_session()` 被调用的
            #     那一刻，上一个会话对象必须**已经**被回收。修前为 True，修后必须 False。
            # ★★ 这个持有者是**受控实验**抓出来的，不是推理出来的：光丢缓存、
            #    光把自己的局部名置 None **都不够**。真正钉住会话的是 `exc` 自己 ——
            #    异常对象挂着 traceback，traceback 挂着**整条栈帧链**，而那些帧的
            #    局部变量/形参里就有 `session`（本函数的局部、rembg 内部的形参）。
            #    只要 `exc` 还在作用域内，这条链就一直替我们握着那块 arena。
            #
            #    探针 `_t_holderprobe.py`（只改"清不清 traceback"这一个变量）：
            #        不清 → 旧会话仍活着 = True     ← 重试时新旧两个 arena 并存
            #        清掉 → 旧会话已回收 = False
            #    所以清 traceback 不是"顺手做的卫生"，它就是这一步能不能成立的关键。
            exc.__traceback__ = None
            _drop_session(info.get("session"))
            session = None      # ★ 断掉本地引用 —— 上一条链断开后，这一行才真起作用
            gc.collect()
            session, info = _load_session()
            if session is None:
                break
        else:
            meta = {"mode": "rembg", **info}
            if failures:
                # 重试成功也要留痕：它说明这台机器的抠图**偶发不稳**，
                # 下一次可能在别处炸 —— 这条痕迹是排查时的第一条线索。
                meta["infer_retried"] = failures
            return out, meta

    raise CutoutError(
        "rembg 推理连续失败（" + "；".join(failures) + "）。"
        "这通常是内存不足引起的瞬时故障，不是这张图的问题 —— "
        "实测一次抠图约需 6—9 GB 可提交内存（birefnet-general-lite，1024² 输入），"
        "按这个量级腾地方："
        "① 关掉占内存的程序，尤其是另一个还在跑抠图的进程"
        "（同机会话各要一份，两个一起就把彼此挤死）；"
        "② 显式改用洪水填充质量略降但结果确定：run.py --cutout floodfill。")


# 抠图有效性阈值：alpha 前景覆盖率高于它 ⇒ 背景几乎没被抠掉。
#
# ★ 为什么必须能**硬失败**而不是"记个提醒"：
#   四周留白是合成上去的画布，所以白底/边缘类校验会**全部假通过**，
#   而产品区内其实仍是原照片的背景。这类图能过校验、却不可上架 ——
#   正是本文件上面警告过的那种情况。
#
# 门槛定在 0.97 而非 0.85：输入是**紧缩(crop)之后**的，一件方形产品
# （杯子、盒子）的覆盖率本来就接近 0.9，用 0.85 会误杀正常输入。
SUSPECT_ALPHA_COVERAGE = 0.97


def alpha_coverage(rgba: Image.Image) -> float:
    """alpha 前景覆盖率（0—1）。纯函数，与 alpha_bbox 一样有多个消费方。

    调用方传**紧缩之后**的图（问的是"产品区域里还有没有残留背景"），
    见 cutout_is_suspect。
    """
    return float((np.asarray(rgba.getchannel("A")) > 16).mean())


def cutout_is_suspect(cut_info: dict, coverage: float) -> str | None:
    """抠图是否没生效。返回原因（人话）或 None。

    `coverage` 由调用方给出，且必须在**紧缩之后**的 alpha 上量 ——
    问的是"产品区域里还有没有残留背景"，不是"整张图有多少前景"。
    把量法和判据分开，是为了让"必须紧缩"这条口径写在文档里，
    而不是隐式地藏在某个函数体里被后来者抄走。

    ★ 一处定义，三个消费方 —— 各自的**反应不同，判据相同**：
        subject.prepare    硬失败（我们的主体，错了整批都错）
        contents_compose   硬失败（内容物抠穿了，白底会假装合规）
        compare_side       只记提醒（竞品是别人的图，抠得糙不影响我们的合规）
    若三处各写一遍阈值，就会出现"主体判它不合格、内容物判它合格"这种自相矛盾。
    """
    if cut_info.get("mode") in ("existing_alpha", "prepared_subject", "passthrough"):
        return None                      # 本来就是抠好的图，不存在"没抠干净"
    if coverage > SUSPECT_ALPHA_COVERAGE:
        return (f"抠图未生效：主体区域 alpha 前景覆盖率 {coverage:.1%}，"
                f"说明背景与主体颜色太接近、没被分离出来。这类图**能通过白底校验**"
                f"（四周留白是合成上去的画布）却不可上架。"
                f"可行修法：① 换对比明显的背景重拍；"
                f"② 直接提供已抠好的透明 PNG")
    return None


def alpha_bbox(rgba: Image.Image):
    """alpha 前景的紧缩外接框。

    公开（去掉下划线）是因为它有两个消费方：
        make_main_image   —— 裁掉多余画布后按占比缩放
        subject.prepare   —— 产出**全体共用的** subject.png（不变量 A）
    公开一个纯函数，胜过让第二个文件抄一遍同样的 5 行。
    """
    a = np.asarray(rgba.getchannel("A"))
    ys, xs = np.where(a > 16)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# ---------------------------------------------------------------- 合成

def _draw_contact_shadow(canvas: Image.Image, x: int, y: int, size: tuple[int, int]) -> Image.Image:
    """柔和接触阴影。默认关闭（严格口径），审核反馈后再开启。"""
    w, h = size
    sh = Image.new("L", canvas.size, 0)
    d = ImageDraw.Draw(sh)
    rx, ry = int(w * 0.40), max(6, int(h * 0.035))
    cx, cy = x + w // 2, y + h - ry // 2
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=70)
    sh = sh.filter(ImageFilter.GaussianBlur(max(8, h // 55)))
    return Image.composite(Image.new("RGB", canvas.size, (150, 150, 150)), canvas, sh)


def filename_for(export: dict, upc: str, slot: dict, seq: int = 1) -> str:
    return export["filename_pattern"].format(
        upc=upc, slot=f"{slot['id']:02d}_{slot.get('role', 'slot')}", seq=seq
    ) + ".jpg"


def make_main_image(
    src_path: str | Path,
    out_dir: str | Path,
    slot: dict,
    export: dict,
    upc: str,
    seq: int = 1,
    force_passthrough: bool = False,
) -> dict:
    """生成位置 1 主图。返回处理报告。"""
    src_path, out_dir = Path(src_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(src_path)
    src_size = img.size

    if force_passthrough:
        rgba, cut_info = img.convert("RGBA"), {"mode": "passthrough", "warning": "未抠图，占比校验无意义"}
    else:
        rgba, cut_info = remove_background(img)

    bbox = alpha_bbox(rgba)
    if bbox is None:
        raise ValueError(f"抠图后未检测到前景主体：{src_path}")

    # 抠图有效性自检：alpha 前景覆盖率接近整图 ⇒ 抠图没生效。
    # 这种情况最危险 —— 所有"边缘类"校验都会**假通过**（因为四周留白是
    # 合成上去的白画布），但产品区内其实是原照片的背景残留。
    alpha_cov = float((np.asarray(rgba.getchannel("A")) > 16).mean())
    cutout_suspect = None
    if cut_info.get("mode") != "passthrough" and alpha_cov > 0.85:
        cutout_suspect = (f"抠图未生效：alpha 前景覆盖率 {alpha_cov:.1%} 接近整图，"
                          f"产品区内很可能残留原背景")

    product = rgba.crop(bbox)
    canvas_side = int(export["long_side_px"])
    fill = float(slot.get("product_fill_pct", 85)) / 100.0

    scale = (canvas_side * fill) / max(product.width, product.height)
    new_size = (max(1, round(product.width * scale)), max(1, round(product.height * scale)))
    product = product.resize(new_size, Image.LANCZOS)

    canvas = Image.new("RGB", (canvas_side, canvas_side), (255, 255, 255))
    x = (canvas_side - new_size[0]) // 2
    y = (canvas_side - new_size[1]) // 2

    if slot.get("contact_shadow"):
        canvas = _draw_contact_shadow(canvas, x, y, new_size)

    canvas.paste(product, (x, y), product)

    out_path = out_dir / filename_for(export, upc, slot, seq)
    canvas.save(out_path, "JPEG", quality=int(export["jpeg_quality"]), optimize=True)

    return {
        "slot_id": slot["id"],
        "path": str(out_path),
        "src": str(src_path),
        "src_size": list(src_size),
        "out_size": [canvas_side, canvas_side],
        "product_size_in_canvas": list(new_size),
        # 主体贴在画布上的**确切位置与尺寸** [x, y, w, h]。
        # 为什么必须由本函数给出：居中规则只在这里定义一次。让调用方自己
        # 按 (canvas - w)//2 重算，就是同一套规则的第二个真相源 ——
        # 而且验收断言"位置 1/2/3 的产品像素同源"必须能拿到这个框。
        "paste_box": [x, y, new_size[0], new_size[1]],
        "product_fill_pct_actual": round(max(new_size) / canvas_side * 100, 2),
        "product_fill_pct_target": slot.get("product_fill_pct", 85),
        "cutout": cut_info,
        "alpha_coverage": round(alpha_cov, 4),
        "cutout_suspect": cutout_suspect,
        "shadow": bool(slot.get("contact_shadow")),
    }
