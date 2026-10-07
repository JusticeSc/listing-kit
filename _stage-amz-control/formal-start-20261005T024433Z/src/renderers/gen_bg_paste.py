"""位置 4 · 场景使用 —— ★ 全链路唯一调用生成模型的一格。

像素来源：**模型生成的环境像素 + 抠好的主体（事后确定性贴入）**。

接缝 α（这是全系统的关键决定）
----------------------------
    模型**只画空背景**，看不见主体。提示词里只描述环境，
    负向词里**无条件排除产品本体**。主体随后由代码贴入 → 主体绝对保真。

    代价：接缝与光影融不进去。这是本格已知的、被明确接受的代价 ——
    背景优先选简单环境（桌面/墙面/单色），不引入超分、重绘、ControlNet。
    「主体不进模型」换来的不是更好看，是**主体一致性从"要验"变成"结构上不可能错"**。

为什么只有这一格可以生成
----------------------
    环境是唯一**没有任何人持有事实**的东西（人工做图时背景也是设计师凭感觉搭的）。
    其余坑位画的是事实：材质长什么样、盒子里有什么、竞品长什么样 —— 生成它们等于编造。

本模块私有资产（下方常量 + build_bg_prompt）
------------------------------------------
    提示词素材放在这里，不放 planner —— 换掉生成方式时不该翻第二个文件。

三个"配置在别处、消费在这里"的字段（都有明确的消费点，不是装饰）
----------------------------------------------------------
    catalog.bg_prompt_hints   → 取景提示池。**改这个文件就能换场景基调**，
                                不需要动一行代码，也不需要靠随机数"碰"出变化。
    brand.forbidden_on_image  → 图上不许出现的词。两处消费：
                                ① 取景提示若命中它 → **弃用该提示**（提示词是人写的，
                                   一句"促销标签"就等于主动邀请模型画那个东西）；
                                ② 追加进负向词 —— 让"不许出现"这条在画面上真的成立，
                                   而不是只写在配置里。
    slot.product_fill_pct     → 主体占画布宽的比例（与位置 2/3/5/6/7 同一套几何）

为什么取景提示是**确定性挑选**而不是随机
--------------------------------------
    同一 (run, 坑位) 必须给同一个提示，否则 `layer=bg` 的重做会换一个场景 ——
    那不是"重做"，那是"换了一张图"，版本对比立刻失去意义。
    想换场景：改 `catalog.bg_prompt_hints`（**改数据**），再重做。
    这与全项目的主张一致：行为变化来自数据，不来自随机数。

生成底什么时候复用（`ctx["reuse_bg"]`）
------------------------------------
    重做的粒度决定背景像素**该不该**变：

        layer=placement  只动主体落点  → 背景没有理由变 → 复用，不调模型
        layer=cutout     只动主体边缘  → 背景没有理由变 → 复用，不调模型
        layer=bg         要的就是换背景 → 重新生成

    这条复用是「位置或大小不对 = 免费」这句话的**实现**。没有它，
    位置 4 会为了把主体挪 20 像素去花一次模型调用 —— 那笔钱买不到任何东西，
    还会顺手换掉背景，让"只是位置不对"这个判断失去意义。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

import imagegen
import placement
import textlayer
from registry import register

# ---------------------------------------------------------------- 提示词素材
# 生成层强制禁字条款：不可省略，否则模型会自作主张画上文字 / 水印 / 假品牌名。
# （实测记录：首轮 qwen-image-3.0 除指定内容外，还自己画了一个水滴 logo 和
#   "THERMO" 字样 —— 那是它虚构的品牌。这就是"文字必须由代码画"的直接证据。）
NO_TEXT_CLAUSE = (
    "画面中不要出现任何文字、字母、数字、汉字、水印、标志、logo、签名、"
    "价格标签、促销角标、边框"
)

# ★ 不变量 B 的实现：**无条件排除产品本体**。
# 这句必须由代码追加，不能指望取景提示里写全 —— 提示词是人写的，会漏。
SUBJECT_EXCLUSION_CLAUSE = (
    "画面为空场景背景，不要出现任何产品、商品、容器、杯、瓶、包装盒、"
    "logo 或其局部"
)

# 负向词：产品本体的英文写法也要列，模型对英文类别词更敏感
SUBJECT_EXCLUSION_NEGATIVE = (
    "product, products, merchandise, item, container, cup, mug, bottle, "
    "packaging, package, box, logo, brand, text, watermark, people, hands"
)

BASE_NEGATIVE = (
    "文字, 字母, 数字, 水印, 标志, logo, 签名, 标签, 价格, 边框, "
    "低质量, 模糊, 畸变, 多余的手指, 重复的物体"
)

# 构图约束：主体是**居中贴入**的（几何规则在 src/placement.py，本格不搞特例），
# 所以背景也必须"中央空置"。这两边一旦不一致，提示词要求的"右侧留白"就会
# 孤零零地空在主体旁边 —— 那不是留白，那是构图偏了。
COMPOSITION_CLAUSE = "中央大面积空置简洁，四周环境自然延展，正方形构图"


def build_bg_prompt(slot: dict, hint: str, banned: list[str] | None = None
                    ) -> tuple[str, str]:
    """拼位置 4 的正/负向提示词。返回 (prompt, negative_prompt)。

    banned 是 `brand.forbidden_on_image` —— 图上不许出现的词。
    它们被追加进负向词，于是"配置里声明的禁令"在画面上真的生效。
    """
    prompt = (f"{hint}，{COMPOSITION_CLAUSE}，{SUBJECT_EXCLUSION_CLAUSE}，"
              f"{NO_TEXT_CLAUSE}，高清，专业摄影布光")
    neg = [SUBJECT_EXCLUSION_NEGATIVE, BASE_NEGATIVE]
    if banned:
        neg.append("、".join(banned))
    return prompt, ", ".join(neg)


def pick_hint(catalog: dict, banned: list[str], slot_id: int
              ) -> tuple[str, list[dict]]:
    """从 `catalog.bg_prompt_hints` 里挑一条取景提示（确定性）。

    返回 (提示词, 被弃用的提示及原因)。**一条不剩就抛错** —— 那说明类目配置
    与品牌禁令已经互相矛盾（提示池里全是"图上不许出现"的词），
    这时候照跑会产出一张不可能合规的图，报错比出图正确。
    """
    hints = [str(h) for h in (catalog.get("bg_prompt_hints") or []) if str(h).strip()]
    kept: list[str] = []
    dropped: list[dict] = []
    for h in hints:
        hit = [w for w in banned if w and w in h]
        (dropped if hit else kept).append({"hint": h, "hit": hit} if hit else h)
    if not hints:
        raise ValueError(
            "类目配置里没有 bg_prompt_hints —— 位置 4 没有取景提示就无从生成。"
            "见 config/catalog/*.yaml")
    if not kept:
        raise ValueError(
            f"bg_prompt_hints 里 {len(hints)} 条提示全部命中 forbidden_on_image "
            f"（{dropped}）—— 类目配置与品牌禁令冲突，先改数据再出图")
    # 确定性：只按坑位号取。不用 random，也不用 seq —— 见模块头说明。
    return kept[slot_id % len(kept)], dropped


def _cover(path: Path, w: int, h: int) -> tuple[Image.Image, dict]:
    """把生成的背景**铺满**画布（允许裁切，绝不补边）。

    为什么是 cover 而不是 fit：背景铺不满时补出来的那圈是**编的像素**，
    而且会形成一条肉眼可见的接缝 —— 位置 5 用 cover 是同一个道理。
    """
    bg = Image.open(path).convert("RGB")
    cov = placement.cover_box(bg.size, w, h)
    out = bg.resize(tuple(cov["scaled"]), Image.LANCZOS).crop(tuple(cov["crop"]))
    return out, {"src_size": list(bg.size), "cover_crop": cov["crop"],
                 "cover_scaled": cov["scaled"], "cover_scale": cov["scale"]}


def assert_subject_excluded(gen: dict) -> None:
    """不变量 B 的守卫：**模型这次有没有看见像素**。看请求体，不看声明。

    判据（三条，缺一不可）：
        mode == "dashscope"  —— 只有**真发了请求**才谈得上"送了什么"。
                                占位图 / 复用生成底压根没发请求 → 无从谈起，不报错。
        request_image_fields —— 由 `imagegen.inclusion_report` 扫描**真实请求体**得出，
                                不是本模块自己声明的。

    为什么值得单独成为一个函数：这是全系统唯一一句"结构保证"的看门人 ——
    「七张图里的杯子是同一个杯子」不靠验，靠**主体像素根本没进过模型**。
    它要是被悄悄删掉，没有任何测试会红，而系统的核心主张已经没了。
    所以它必须能被探针**直接打中**（evals/probes/invariants.py 的 B 段）。
    """
    img_fields = list(gen.get("request_image_fields") or [])
    if gen.get("mode") == "dashscope" and img_fields:
        raise RuntimeError(
            f"不变量 B 被破坏了：这次生成请求里带着图像字段 {img_fields} —— "
            f"模型能看见像素。「主体绝对保真」此前是**结构保证**"
            f"（请求里根本没有主体像素），此刻退化成只是一个期望；"
            f"七张图里的杯子可能变成七个不同的杯子，而那正是这套系统存在的理由。"
            f"若确实要送参考图：必须在本文件里显式说明送的是什么、如何排除主体，"
            f"并把 negative_prompt 与校验一并改掉 —— 不许悄悄多送一张。")


@register("gen_bg_paste", label="生成背景 + 贴主体",
          summary="模型只画空背景 → 主体确定性贴入（★唯一调模型）",
          calls_model=True, backgrounds=("generated",))
def render(slot: dict, ctx: dict) -> dict:
    export = ctx["export"]
    catalog = ctx.get("catalog") or {}
    brand = ctx.get("brand") or {}
    plan = ctx["plan"]
    W = H = int(export["long_side_px"])
    run_dir = Path(ctx["run_dir"])

    subject = ctx.get("subject")
    if not subject:
        # 契约违约，不是用户错误 —— 必须响。
        raise RuntimeError(
            "gen_bg_paste 需要主体，但 ctx['subject'] 是空的 —— "
            "说明编排器没有为本次 run 准备 subject.png（见 src/subject.py）")

    banned = [str(w) for w in (brand.get("forbidden_on_image") or []) if str(w).strip()]
    hint, dropped = pick_hint(catalog, banned, int(slot["id"]))
    prompt, negative = build_bg_prompt(slot, hint, banned)

    # 生成底先落在 raw/ 里：它是**可重做**的物质基础 —— `layer=placement/cutout` 的
    # 重做直接复用它（背景像素本来就该不变），`layer=bg` 才会覆盖它。
    (run_dir / "raw").mkdir(exist_ok=True)
    gen_path = run_dir / "raw" / f"slot{slot['id']:02d}_gen.jpg"

    reuse = ctx.get("reuse_bg")
    if reuse and Path(reuse).exists():
        # 复用的理由要说清：这不是"缓存命中"，而是**这一档重做本来就不该换背景**。
        # 只动了主体落点（placement）或主体边缘（cutout），背景像素没有任何理由变。
        gen = {"mode": "reused", "path": str(reuse), "model": None,
               "size": list(Image.open(reuse).size), "warning": None,
               "reused_bg": str(reuse)}
    else:
        gen = imagegen.generate_image(prompt, negative, gen_path,
                                      model=ctx.get("model") or None, size_px=W)

    # ★ 不变量 B：**声明由请求体推导，不是写下来的**（见 imagegen.inclusion_report）。
    #
    #   此前这里写的是硬编码的 `"subject_excluded_from_model": True` ——
    #   一句声明，没有任何东西在验它。将来给 generate_image 加参考图参数那天
    #   （那正是"学参考库编辑类技能"的第一步），这行会继续写 True：变成假话，
    #   不报错、不进任何报表。所以改成：先看这次真发出去的请求里有没有像素字段。
    #
    #   守卫抽成了一个**有名字的纯函数**：没名字的内联 if 只能靠"跑完整个渲染流程"
    #   才碰得到，而那种探针没人愿意跑 —— 于是它实际上是没被验的。
    assert_subject_excluded(gen)
    img_fields = list(gen.get("request_image_fields") or [])
    real_call = gen.get("mode") == "dashscope"

    canvas, cover = _cover(Path(gen["path"]), W, H)

    # ---- 主体：贴进整个画布（位置 4 没有文字条，所以可用区就是全画布）
    src = Image.open(subject["path"]).convert("RGBA")
    spot = placement.fit_region(src.size, W, H,
                               fill_pct=float(slot.get("product_fill_pct", 55)))
    size = (spot["w"], spot["h"])
    prod = src.resize(size, Image.LANCZOS)
    canvas.paste(prod, (spot["x"], spot["y"]), prod)

    # ---- 落盘：交回文字层（位置 4 text=none → 它直接存成品）
    rep = textlayer.finish(canvas, run_dir, plan, slot, brand, export,
                           ctx["upc"], palette=catalog.get("palette") or {},
                           seq=ctx.get("seq", 1))

    rep.update({
        "renderer": "gen_bg_paste",
        # ★ 无 key 时 imagegen 会退化成占位背景 —— 那不是产物，必须自报家门，
        #   否则它会以"真实场景图"的身份流到运营手上。
        "placeholder": gen.get("mode") == "mock",
        "subject_sha256": subject["sha256"],
        "subject_source": subject["source"],
        "paste_box": [spot["x"], spot["y"], size[0], size[1]],
        # 不变量 B 的证据：由**请求体**推导（imagegen.inclusion_report）。
        #   · 真发了请求且请求体无图像字段 → True（证明）
        #   · 占位图（没 key，压根没发请求）/ 复用生成底 → None（**无从谈起**）
        #     对一次没发生的请求宣称"我没把主体送出去"是句废话；
        #     记 null，与 model_calls_used 的 null 口径一致。
        "subject_excluded_from_model": (True if real_call else None),
        "subject_exclusion_basis": {
            "basis": ("请求体里没有图像字段（本次真发了请求）" if real_call
                      else f"本次没发请求（mode={gen.get('mode')}）—— 无从谈起"),
            "request_image_fields": img_fields,
            "image_inputs_in_signature": gen.get("image_inputs_in_signature") or [],
            "mode": gen.get("mode"),
        },
        # ★ 复用上一轮生成底时记下用了哪一张。
        #   它是**报告契约的一部分**，所以要有一个稳定的名字：通用消费方
        #   （orchestrator.redo 数"这一档花了几次调用"、审核台算成本）读的就是
        #   这一个键。写成 generation.reused_from 那样的嵌套私名，消费者就只能
        #   靠"猜路径"去取 —— M6 验收第一次跑就是这么红的两条。
        "reused_bg": gen.get("reused_bg"),
        "generation": {
            "mode": gen.get("mode"),
            "model": gen.get("model"),
            "requested_size": gen.get("requested_size"),
            "size": gen.get("size"),
            "hint": hint,
            "hints_dropped": dropped,
            "forbidden_on_image_used": banned,
            "negative_prompt_len": len(negative),
            "negative_prompt_truncated": len(negative) > imagegen.NEG_PROMPT_MAX,
            "prompt": prompt,
            "negative_prompt": negative,
            "note": gen.get("warning"),
            # 推理重试过（rembg 偶发 bad allocation，见 synth.INFER_ATTEMPTS）
            "infer_retried": gen.get("infer_retried"),
            **cover,
        },
    })
    return rep
