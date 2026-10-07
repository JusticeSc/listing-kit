"""渲染器注册表：把「像素怎么来」做成可插拔的一层。

它解决的是什么
--------------
v1 用 `render_path = compose | generate | generate_then_text` 这**一个枚举**
同时表达「像素怎么来」和「有没有字」，于是每多一种组合就得加一个枚举值。

拆成 `renderer × text` 两个正交字段之后：

    加一种像素来源  →  在 src/renderers/ 放一个文件（连登记表都不用改）
    要不要文字      →  slots.yaml 里一个字段

编排器只做 `get(slot["renderer"])(...)`，**不允许出现 `slot["id"] ==`** ——
那是把坑位行为写回代码，等于把"可扩展"退回"预留了位置"。

元数据是**声明式**的（label / summary / calls_model 在登记时给出），
不是"跑一次看它返回什么"：
    · --dry-run 要能算出"几次模型调用"，不能为此真的去渲染；
    · schema 校验会遍历所有渲染器 —— 若靠调用探测，M3 之后
      一次配置校验就会触发真实出图。这类副作用必须从源头断掉。

加载方式
--------
按**目录扫描**加载 src/renderers/*.py（不写 import 清单）。
这样"加一个 renderer"字面意义上就是"加一个文件" —— 没有第二处要改的地方。
以下划线开头的文件被跳过，用作共享工具（如 _placeholder.py）。

导入约定：全项目统一**扁平导入**（`from registry import ...`），
入口模块（schema.py / orchestrator.py / run.py）负责把 src/ 放进 sys.path。
不要用 `src.registry` —— 那会造出第二个模块对象，注册表就有两份了。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Callable

RENDERER_DIR = Path(__file__).resolve().parent / "renderers"

# name -> {fn, label, summary, calls_model}
_REGISTRY: dict[str, dict[str, Any]] = {}


def _src_of(fn: Callable) -> str:
    """函数**定义所在**的文件路径。

    为什么要按文件判重而不是按模块对象判重（这条是实测撞出来的）：
    `load_all()` 用合成的模块名（`kit_renderer_xxx`）执行渲染器文件，所以
    同一个文件可以有**两个模块对象**（一个是 load_all 造的，一个是有人
    `from renderers import xxx` 造出来的）。按对象判重就会把"同一个渲染器被加载
    了两次"误报成"两个渲染器抢名字"，而前者是完全正常的。
    真正的冲突是**两个不同的文件**登记同一个名字 —— 那才该炸。
    """
    code = getattr(fn, "__code__", None)
    path = getattr(code, "co_filename", "") or ""
    return os.path.normcase(os.path.abspath(path)) if path else str(fn.__module__)


def register(name: str, *, label: str = "", summary: str = "",
             calls_model: bool = False,
             backgrounds: tuple[str, ...] = (),
             cuts: tuple[str, ...] = ()) -> Callable:
    """把一个函数登记为渲染器。

    calls_model 必须由渲染器自己声明：它决定"七张图要调几次模型"，
    而这个数字在 --dry-run 阶段就要算出来（那时一次都不能真调）。
    重复登记同名渲染器 → 直接报错（不许静默覆盖）。
    判重按**定义所在文件**（见 _src_of）：同一个文件被加载两次是正常的
    （load_all 与显式 import 会各造一个模块对象），两个不同文件抢名字才是冲突。

    backgrounds —— 本渲染器**能产出的**背景取值（空 = 不做限定）。
    为什么需要它：表里的 `background` 字段原先没有任何渲染器去读（每个渲染器
    都把自己的底写死了），于是一个字段一个解释者的纪律在这里断了 ——
    "位置 2 用 compose_white + background: palette"能过校验，而 compose_white
    根本不看 palette。渲染器声明它接受的集合，schema 就能交叉拦住这类不匹配。
    这也让 `background` 从"描述性字段"变成"被校验的契约"。

    cuts —— 本渲染器**要求先抠好**的素材名（`needs` 的子集，如 `("competitor",)`）。
    为什么要由渲染器声明、而不是编排器按渲染器名特判：那就是 `slot["id"] ==`
    的姊妹错误 —— 把"像素怎么来"写回编排器。

    为什么这些素材必须**提前、集中**抠好，而不是渲染器用的时候自己抠：
      1. **顺序**（实测教训）：抠图推理会偶发抓不到内存（ORT bad allocation /
         numpy MemoryError）。同一个调用在进程刚起来时稳、在跑完一次 55s 的
         云端生成之后就不稳了。满素材 run 里位置 6/7 的抠图恰好落在后半段，
         实测因此整格失败。把三处抠图都挪到模型调用**之前**，等于让它们都发生在
         进程最清爽的时候。
      2. **不烧冤枉钱**：抠图失败就不该再去调模型（这条规矩本来就在主体那一步
         写着 —— 只是当时只管了主体）。集中之后，任何抠图失败都在花钱之前暴露。
      3. **一轮只抠一次**：那些素材跑完这一轮就不再需要重抠，于是
         `--layer placement` 之类只动位置的重做**不必再花 25s 重抠一遍**，
         而且产出的像素与上一版**逐字节一致**（否则"只改了位置"这句话就不成立）。
    """

    def deco(fn: Callable) -> Callable:
        prev = _REGISTRY.get(name)
        if prev is not None and _src_of(prev["fn"]) != _src_of(fn):
            raise ValueError(
                f"渲染器名 {name!r} 被重复登记："
                f"已由 {prev['fn'].__module__}（{_src_of(prev['fn'])}）登记，"
                f"现被 {fn.__module__}（{_src_of(fn)}）再次登记。名字必须唯一。")
        _REGISTRY[name] = {"fn": fn, "label": label or name,
                           "summary": summary, "calls_model": bool(calls_model),
                           "backgrounds": tuple(backgrounds),
                           "cuts": tuple(cuts)}
        return fn

    return deco


def get(name: str) -> Callable:
    """取渲染器。未登记的名字 → 报错并列出可用名字（不静默退化）。"""
    if name not in _REGISTRY:
        raise KeyError(
            f"渲染器 {name!r} 未登记。可用：{'、'.join(known()) or '（空）'}")
    return _REGISTRY[name]["fn"]


def known() -> list[str]:
    """已登记的渲染器名（字典序，稳定输出便于比对）。"""
    return sorted(_REGISTRY)


def calls_model(name: str) -> bool:
    """该渲染器是否调用生成模型（声明式，不执行渲染）。"""
    return bool(_REGISTRY.get(name, {}).get("calls_model"))


def backgrounds_of(name: str) -> tuple[str, ...]:
    """该渲染器声明的**可产出**背景集合（空 = 不做限定）。

    消费方：src/schema.py —— 交叉校验 坑位.background 与 渲染器声明 是否匹配。
    """
    return tuple(_REGISTRY.get(name, {}).get("backgrounds") or ())


def cuts_of(name: str) -> tuple[str, ...]:
    """该渲染器声明**要求先抠好**的素材名（空 = 它不用抠任何素材）。

    消费方有两个，都靠它避免"按渲染器名特判"：
        src/orchestrator.py  算出这一轮要先抠哪几样（提前、集中抠）
        src/schema.py        交叉校验 cuts ⊆ needs
    """
    return tuple(_REGISTRY.get(name, {}).get("cuts") or ())


def label_of(name: str) -> str:
    return str(_REGISTRY.get(name, {}).get("label") or name)


def summary_of(name: str) -> str:
    return str(_REGISTRY.get(name, {}).get("summary") or "")


def describe() -> dict[str, dict[str, Any]]:
    """名字 → 元数据，供 --dry-run 与界面展示。"""
    return {n: {"label": v["label"], "summary": v["summary"],
                "calls_model": v["calls_model"]}
            for n, v in sorted(_REGISTRY.items())}


def load_all(*, reload: bool = False) -> list[str]:
    """扫描 src/renderers/*.py 并执行，触发各模块的 @register。

    返回已登记的名字列表。模块级 import 错误会原样抛出（不吞）——
    渲染器加载失败属于启动期故障，必须响。

    渲染器目录会被加进 sys.path，让渲染器之间可以用扁平名互相引用
    （`from _placeholder import placeholder`），与全项目导入风格一致。
    """
    renderer_dir = str(RENDERER_DIR)
    if renderer_dir not in sys.path:
        sys.path.insert(0, renderer_dir)

    for f in sorted(RENDERER_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        mod_name = f"kit_renderer_{f.stem}"
        if mod_name in sys.modules and not reload:
            continue
        spec = importlib.util.spec_from_file_location(mod_name, f)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载渲染器模块：{f}")
        mod = importlib.util.module_from_spec(spec)
        # 必须先登记进 sys.modules，装饰器内自省才拿得到模块信息
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
    return known()
