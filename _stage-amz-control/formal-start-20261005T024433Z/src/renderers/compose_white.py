"""位置 1 · 主图 —— 纯白底居中合成。

像素来源：**`subject.png`（本 run 唯一的那一份主体）+ 常量纯白**。零模型调用。

为什么这一格绝不能交给模型
--------------------------
    主图是搜索结果页里与几十个竞品并排的那一张，平台强制"纯白底 + 无文字 +
    无道具"，自由度为零。它要的不是"画一张图"，是"把实物干净居中地呈现"——
    用生成模型做这件事 = 用概率工具做确定性任务：它会加不存在的细节、会变形、
    而这一张的容错是零（违规 = listing 降权 / 下架）。

为什么它读 subject.png 而不是自己抠 front
-----------------------------------------
    不变量 A：主体只有一份。抠图已在 `src/subject.py` 做过了。
    这里若再抠一次，位置 1 与位置 2 的主体轮廓就可能不一致（每次抠图都是
    一次独立推断），而抠图失败会变成七个地方的七条日志。
    **本文件里没有抠图调用** —— 这就是那条不变量的代码级证据。

落地方式：包住 synth.make_main_image，不改它的合成逻辑
---------------------------------------------------
    它原本的 `force_passthrough` 是给"输入已是白底图"用的；这里输入是
    **已抠好的 RGBA**，效果等价（跳过抠图步、直接用 alpha 做遮罩）。
    唯一需要就地覆盖的是它报告里的 `cutout.warning`（那句是为"未抠图的白底图"
    写的，对本次语义不对）—— 改的是报告字段，不是合成逻辑。
"""
from registry import register

import synth


@register("compose_white", label="纯白底合成",
          summary="subject.png → 纯白画布居中", calls_model=False,
          backgrounds=("pure_white",))
def render(slot: dict, ctx: dict) -> dict:
    subject = ctx.get("subject")
    if not subject:
        # 这是编排器与渲染器之间的契约违约，不是用户错误 —— 必须响。
        raise RuntimeError(
            "compose_white 需要主体，但 ctx['subject'] 是空的 —— "
            "说明编排器没有为本次 run 准备 subject.png（见 src/subject.py）")

    rep = synth.make_main_image(
        src_path=subject["path"],
        out_dir=ctx["run_dir"],
        slot=slot,
        export=ctx["export"],
        upc=ctx["upc"],
        seq=ctx.get("seq", 1),
        force_passthrough=True,          # 主体已经抠好了，不要再抠一次
    )

    rep["renderer"] = "compose_white"
    rep["placeholder"] = False
    rep["subject_sha256"] = subject["sha256"]
    rep["subject_source"] = subject["source"]
    # 覆盖那句语义不对的警告（见模块头说明），并交代主体的真实来路。
    rep["cutout"] = {
        "mode": "prepared_subject",
        "cutout_mode": (subject.get("cutout") or {}).get("mode"),
        "alpha_coverage": subject.get("alpha_coverage"),
    }
    return rep
