# -*- coding: utf-8 -*-
"""离线走查的界面（Phase 2 / D2.R1）。

八页：0 开始 → 1 任务 → 2 计划 → 3 提示词 → 4 候选 → 5 返工 → 6 合成 → 7 导出。

三条界面纪律（不是风格问题）：

* **只渲染权威状态。** 页面内容全部来自 `app/offline.py` 装配出来的对象；页面自己
  不算、不猜、不记状态。读不到就写"未就绪"，不显示一个看起来成功的空壳。
* **不暴露内部术语。** 页面上不出现 JSON、接口名、模型参数、字段名；对象只用业务说法。
* **假动作自己承认。** 本期没有真的发生的事（生成、重做、导出）都在动作旁边写明
  "离线演示，不做这件事"。
"""

from __future__ import annotations

import html

from app import offline as OFF

# (路径, 导航名, 页面标题)。顺序就是用户走的顺序，也是 --check 依次渲染的顺序。
PAGES = (
    ("", "开始", "开始之前：这是什么、会做什么"),
    ("task", "任务", "这次要做的东西"),
    ("workbench", "工作台", "一张图一处：方案、提示词、候选、返工、选中"),
    ("export", "导出", "交付包里有什么"),
)

PLATFORM_SLOT_LABEL = {"main": "主图", "scene": "场景图", "detail": "细节图"}
SCENE_LABEL = {"studio-white": "纯白影棚", "kitchen-lifestyle": "厨房生活场景"}
COMPOSITION_LABEL = {"studio-centered": "居中构图", "three-quarter-hero": "四分之三侧面构图"}
VARIATION_LABEL = {"scene": "场景", "lighting": "光线", "composition": "构图"}
VIEW_LABEL = {"front-full": "正面全身", "upper-closeup": "上部近景", "lower-detail": "底部近景"}
CHECK_RULE_CN = {"decodable": "能正常打开", "min_long_side_px": "边长足够",
                 "aspect_ratio": "长宽比符合", "max_file_mb": "文件大小符合",
                 "export_format": "导出格式"}
REVIEWER_CN = {"project-operator": "操作者自签（非第三方）"}
SELECTED_BY_CN = {"user": "本次走查的操作人"}


def _lab(mapping: dict, value: str) -> str:
    """展示翻译：内部代号转业务说法，不认识的原样保留。"""
    return mapping.get(value, value)


def h(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _ul(items, cls: str = "") -> str:
    body = "".join(f"<li>{i}</li>" for i in items)
    return f'<ul class="{cls}">{body}</ul>'


def _card(title: str, body: str, *, kind: str = "", note: str = "") -> str:
    tail = f'<p class="note">{note}</p>' if note else ""
    return (f'<section class="card {kind}"><h3>{h(title)}</h3>{body}{tail}</section>')


def _kv(rows) -> str:
    body = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    return f'<table class="kv">{body}</table>'


def _outcome(res) -> str:
    """把一个环节的结果说成人话。没有结果就是"未就绪"，不装作通过。"""
    if res is None:
        return '<span class="st unknown">未就绪</span>'
    tone = {"accepted": "ok", "business_reject": "warn", "needs_human": "warn",
            "technical_fail": "bad", "unknown": "unknown"}.get(res.outcome, "bad")
    words = {"accepted": "通过", "business_reject": "需要人来定", "needs_human": "需要人确认",
             "technical_fail": "技术失败", "unknown": "未知"}.get(res.outcome, res.outcome)
    why = "；".join(res.notes[:2])
    tail = f'<span class="why">{h(why)}</span>' if why else ""
    return f'<span class="st {tone}">{h(words)}</span>{tail}'


CSS = """
:root{--ink:#1b1f24;--sub:#5c6672;--line:#e2e6ea;--bg:#f6f7f9;--card:#fff;
--ok:#1f7a45;--warn:#8a6100;--bad:#a52a2a;--accent:#1d5fa8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.65 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
header{background:#fff;border-bottom:1px solid var(--line);padding:14px 22px}
.brand{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.brand h1{font-size:19px;margin:0}
.brand .sku{color:var(--sub);font-size:13px}
.badge{display:inline-block;background:#fff4d6;color:var(--warn);border:1px solid #f0dca8;
border-radius:999px;padding:2px 10px;font-size:12px}
nav{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}
nav a{padding:5px 11px;border-radius:7px;text-decoration:none;color:var(--sub);
border:1px solid transparent;font-size:14px}
nav a:hover{background:var(--bg)}
nav a.on{background:var(--accent);color:#fff}
main{max-width:1020px;margin:0 auto;padding:22px}
h2{font-size:20px;margin:0 0 4px}
.lead{color:var(--sub);margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin:0 0 16px}
.card h3{margin:0 0 10px;font-size:16px}
.card.warn{border-color:#f0dca8;background:#fffdf6}
.card.bad{border-color:#e8b4b4;background:#fff8f8}
.card.ok{border-color:#bfe0cd;background:#f7fdf9}
.note{color:var(--sub);font-size:13px;margin:10px 0 0}
table{border-collapse:collapse;width:100%}
table.kv th{text-align:left;width:190px;color:var(--sub);font-weight:600;
padding:5px 10px 5px 0;vertical-align:top}
table.kv td{padding:5px 0;vertical-align:top}
table.grid td,table.grid th{border:1px solid var(--line);padding:7px 9px;
text-align:left;vertical-align:top;font-size:14px}
table.grid th{background:#fafbfc;color:var(--sub);font-weight:600}
pre{background:#fbfcfd;border:1px solid var(--line);border-radius:8px;padding:12px;
white-space:pre-wrap;word-break:break-word;font:13px/1.6 Consolas,"Courier New",monospace;
max-height:420px;overflow:auto}
textarea{width:100%;min-height:150px;border:1px solid var(--line);border-radius:8px;
padding:10px;font:13px/1.6 Consolas,"Courier New",monospace}
input[type=text]{width:100%;border:1px solid var(--line);border-radius:8px;padding:9px 10px}
button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:9px 15px;
font-size:14px;cursor:pointer}
button.ghost{background:#fff;color:var(--accent);border:1px solid var(--accent)}
button[disabled]{background:#c9d2dc;cursor:not-allowed}
select{border:1px solid var(--line);border-radius:8px;padding:9px 10px;background:#fff}
.st{display:inline-block;border-radius:6px;padding:1px 8px;font-size:13px;margin-right:8px}
.st.ok{background:#e6f4ec;color:var(--ok)}
.st.warn{background:#fdf1d8;color:var(--warn)}
.st.bad{background:#fbe7e7;color:var(--bad)}
.st.unknown{background:#eceff2;color:var(--sub)}
.why{color:var(--sub);font-size:13px}
.grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.cand{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px}
.cand img{width:100%;border-radius:7px;display:block;background:#000}
.cand h4{margin:10px 0 6px;font-size:15px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.chip{background:#eef2f6;color:var(--sub);border-radius:999px;padding:2px 9px;font-size:12px}
.chip.lock{background:#e9f0fa;color:var(--accent)}
footer{color:var(--sub);font-size:13px;text-align:center;padding:26px 22px 34px}
.steps li{margin:2px 0}
.flash{background:#eef6ff;border:1px solid #cfe2f8;border-radius:9px;padding:11px 14px;margin:0 0 16px}
"""


def layout(page: str, session, body: str, *, flash: str = "") -> str:
    nav = "".join(
        '<a href="/{p}" class="{c}">{l}</a>'.format(p=path, c="on" if path == page else "",
                                                   l=h(label))
        for path, label, _ in PAGES)
    name = session.card.get("display_name") or session.sku
    head = f'<div class="flash">{h(flash)}</div>' if flash else ""
    return (
        "<!doctype html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{h(name)} · 商品图片演示</title><style>{CSS}</style></head>\n"
        "<body><header>\n"
        f'<div class="brand"><h1>{h(name)}</h1><span class="sku">虚构演示商品</span>'
        '<span class="badge">离线演示 · 不联网 · 不花钱</span></div>\n'
        f"<nav>{nav}</nav></header>\n"
        f"<main>{head}{body}</main>\n"
        "<footer>虚构演示商品，不用于真实上架、对外宣传或平台审核。本页所有结论来自"
        "已冻结的检查记录；页面本身不生成、不导出、不改任何文件。</footer>\n"
        "</body></html>"
    )


def _blocked(session, page: str) -> str:
    """流程被挡在某个环节时，页面只讲这一件事，不摆一堆空壳。"""
    rows = []
    for cid, res in session.blockers():
        rows.append((cid, _outcome(res)))
    body = [
        "<h2>这一步还走不下去</h2>",
        '<p class="lead">下面的环节没有通过，后面的页面因此没有内容。缺料要补料，'
        "修数据而不是放宽检查。</p>",
        _card("卡在哪儿", _kv(rows), kind="bad"),
    ]
    return layout(page, session, "".join(body))


# ------------------------------------------------------------------ 页 0 开始
def page_home(session, *, flash: str = "") -> str:
    card = session.card
    steps = [
        "先确认这个商品是什么、它的素材齐不齐",
        "去工作台：一张图一处，方案、提示词、候选、返工、选中都在同一页",
        "在候选中挑一张成品；不满意就说明哪里不满意，系统只改该改的那一处",
        "去导出看一眼交付包：缺的图会明说，能交付的部分先预览",
    ]
    fake = "".join(
        f"<tr><td>{h(a)}</td><td>{h(b)}</td><td><b>{h(c)}</b></td></tr>"
        for a, b, c in OFF.FAKE_ACTIONS)
    body = [
        f'<h2>{h(card.get("display_name") or session.sku)}</h2>',
        '<p class="lead">这是一个用来演示「商品图片从计划到交付」的本地工具。'
        "它现在用的是内置的虚构商品，所以你可以随便点、随便试，不会碰到真实业务数据。</p>",
        _card("三句话讲清楚这套东西",
              _ul(["商品长什么样、哪些特征必须保持，由一份<b>事实卡</b>先定下来；"
                   "后面每张图都要拿这张卡对一遍。",
                   "系统先给一份默认方案（哪几张图、每张干什么、怎么描述），"
                   "你不需要自己写提示词；想改也能改，改的是实际发给模型的那段话。",
                   "生成结果不自动算数：事实要过关、人要逐张给结论，"
                   "最后选中的那张才是成品。"]),
              kind="ok"),
        _card("这个商品是虚构的",
              _ul([h(x) for x in (card.get("disclaimers") or [])])),
        _card("现在这一版是怎么跑的",
              '<p>平台：Amazon US。生成模型：阿里云百炼的 <b>qwen-image-3.0</b>'
              "（图生图）。商品参考图会真的进入请求 —— 这是正式路径的硬前提，"
              "没有\"拒绝外发以后改用纯文字生成\"这种替代路线。</p>"
              '<p class="note">你现在看到的这一版是<b>离线演示</b>：用已经跑出来的真实候选'
              "把后面的流程走一遍，不联网、不花钱、不改任何文件。</p>"),
        _card("哪些按钮是假的（说在前面）",
              '<table class="grid"><tr><th>动作</th><th>正式版会做什么</th>'
              f"<th>这一版</th></tr>{fake}</table>",
              kind="warn",
              note="这三个动作在下面每一页出现时，旁边都会再写一次。"),
        _card("你会依次看到什么", _ul(steps, cls="steps")),
    ]
    return layout("", session, "".join(body), flash=flash)


# ------------------------------------------------------------------ 页 1 任务
def page_task(session, *, flash: str = "") -> str:
    if session.blockers():
        return _blocked(session, "task")
    card = session.card
    identity = card.get("identity") or {}
    ref = session.steps["PC-01"]
    views = ref.payload.get("views") or []
    view_rows = "".join(
        f"<tr><td>{h(_lab(VIEW_LABEL, v.get('view_id')))}</td><td>{h(v.get('role'))}</td>"
        f"<td>{h((v.get('file') or '').split('/')[-1])}</td>"
        f"<td>{h((v.get('sha256') or '')[:12])}…</td></tr>" for v in views)
    shots = session.shots()
    shot_rows = "".join(
        f"<tr><td>{h(sh.get('shot_id'))}</td>"
        f"<td>{h(PLATFORM_SLOT_LABEL.get(sh.get('platform_slot'), sh.get('platform_slot')))}</td>"
        f"<td>{h(sh.get('purpose'))}</td>"
        f"<td>{h('、'.join(_lab(VIEW_LABEL, v) for v in (sh.get('reference_views') or [])))}</td></tr>" for sh in shots)
    missing = [sh["shot_id"] for sh in shots
               if not session.candidates_of_shot(sh["shot_id"])]
    have = session.candidates_of_shot(session.candidate_shot)
    facts = session.steps["PC-02"].payload.get("facts") or []
    unknown = session.steps["PC-02"].payload.get("unknowns") or []
    body = [
        "<h2>这次要做的东西</h2>",
        '<p class="lead">一个虚构保温杯的一组 Amazon US 商品图。下面的素材检查、'
        "事实和计划全部来自这个商品的资料包，不是写死在程序里的。</p>",
        _card("商品是什么",
              _kv([("商品名", h(card.get("display_name"))),
                   ("品类", h(card.get("product_class"))),
                   ("外观", h(identity.get("form"))),
                   ("用途", h(identity.get("usage"))),
                   ("资料版本", h(card.get("version")))]),
              note="这是虚构演示商品，不对应任何真实品牌或在售产品。"),
        _card("素材齐不齐", _outcome(ref) +
              f'<table class="grid"><tr><th>视图</th><th>用途</th><th>文件</th>'
              f"<th>指纹</th></tr>{view_rows}</table>",
              kind="ok" if ref.accepted else "bad",
              note="每个文件都逐一对过指纹；素材对不上就必须补料或恢复原文件，"
                   "不许就地改写素材来过检。"),
        _card("要产出这几张",
              f'<table class="grid"><tr><th>图</th><th>类型</th><th>这一张要什么</th>'
              f"<th>看哪张参考图</th></tr>{shot_rows}</table>",
              note="张数不是配置项：它来自平台坑位与素材齐套的交集。"),
        _card("现在缺什么",
              _ul([f"<b>{h(sid)}</b>：还没有候选，需要正式生成（离线演示不生成）"
                   for sid in missing]
                  + ([f"<b>{h(session.candidate_shot)}</b>：已有 {len(have)} 张真实候选，"
                      "这一轮可以完整走一遍审核、返工与选择"] if have else [])),
              kind="warn" if missing else "ok"),
        _card(f"事实先定下来（{len(facts)} 条）",
              _ul([f"<b>{h(f.get('id'))}</b> {h(f.get('claim'))}" for f in facts]) +
              "<p class=\"note\">这些字段目前保持<b>未知</b>："
              + h("、".join(u.get("field") or "" for u in unknown))
              + " —— 未确认的东西不会被写成事实，也不会进提示词。</p>"),
    ]
    return layout("task", session, "".join(body), flash=flash)
# ------------------------------------------------------------------ 页 4 候选
FACT_VERDICT_CN = {"pass": "通过", "fail": "不符合", "risk": "有风险，待人工确认",
                   "needs_human": "待人工确认", "unknown": "还判不了"}
VISUAL_VERDICT_CN = {"keep": "可以留", "redo": "要重做", "reject": "不要"}
CHECK_VERDICT_CN = {"pass": "通过", "fail": "不通过", "not_applicable": "这一项不适用"}
OWNER_CN = {"human": "人给的", "deterministic": "机器按规则判的", "model": "模型给的"}


def _owner_label(value: str) -> str:
    if not value:
        return "还没人给结论"
    return OWNER_CN.get(value, value)
# ------------------------------------------------------------------ 页 5 返工
# 原因码的中文说法只是显示用；分类与「只改什么」的权威在 demo/core/back_chain.py。
REASON_CN = {
    "not_decodable": "图片打不开",
    "wrong_format": "文件格式不对",
    "size_too_small": "尺寸太小",
    "aspect_mismatch": "长宽比不对",
    "file_too_large": "文件太大",
    "background_clutter": "背景太乱",
    "composition_weak": "构图不好",
    "lighting_harsh": "光线太硬",
    "product_identity": "商品跟原来的不是同一个",
    "product_structure": "商品结构不对",
    "exact_text_needed": "需要精确的文字",
}


def _rework_result(session) -> str:
    res = session.rework
    if not res:
        return '<p class="why">还没有选过原因。</p>'
    outcome = res.get("outcome")
    notes = "；".join(res.get("notes") or [])
    if outcome != "accepted":
        return f'<p><span class="st warn">这一步要人来定</span>{h(notes)}</p>'
    change = res["payload"]["change"]
    cat = change.get("category")
    rows = [("你选的原因", h(REASON_CN.get(change.get("reason_code"), change.get("reason_code")))),
            ("归到哪一类", h(OFF.CATEGORY_LABEL.get(cat, cat))),
            ("只改这些", h("、".join(change.get("changes") or []) or "——")),
            ("为什么", h(change.get("why")))]
    extra = ""
    if change.get("new_prompt_version"):
        nv = change["new_prompt_version"]
        extra = _card("这一次的提示词会怎么变",
                      f'<p>新版本 <b>{h((nv.get("version_id") or "")[:12])}…</b>，'
                      f'上一版 {h((nv.get("parent") or "")[:12])}… 原样保留。</p>'
                      f"<pre>{h((nv.get('diff') or {}).get('unified'))}</pre>",
                      note="只加了一句针对这个原因的调整；带锁的事实段一个字没动。")
    if cat == "identity":
        extra = _card("这一类需要你先给素材",
                      "<p>商品认错或结构不对，靠改描述解决不了。要换参考图或换路线，"
                      "而「用哪张参考图」由人来定，系统不会自己挑。</p>", kind="warn")
    untouched = res["payload"].get("untouched_shots") or []
    keep = "".join(
        f"<tr><td>{h(u.get('shot_id'))}</td><td>{len(u.get('candidate_sha256') or [])} 张</td>"
        f"<td>{h(u.get('submit_count'))}</td></tr>" for u in untouched)
    return (_kv(rows) + extra
            + _card("哪些不动",
                    '<table class="grid"><tr><th>图</th><th>候选</th>'
                    f"<th>这次提交次数</th></tr>{keep}</table>",
                    note="旧候选一张都不删；没被点名的图连一次提交都不会发生。")
            + '<p class="note"><b>离线演示，不产生新候选。</b>'
              "正式版这里会真的开一次新的生成尝试。</p>")
# ------------------------------------------------------------------ 页 7 导出
def page_export(session, *, flash: str = "") -> str:
    if session.blockers():
        return _blocked(session, "export")
    shots = [sh["shot_id"] for sh in session.shots()]
    rows = ""
    for sid in shots:
        if session.selection and sid == session.candidate_shot:
            state = '<span class="st ok">已选定</span>'
            detail = h(session.selection.get("candidate_id"))
        elif session.candidates_of_shot(sid):
            state = '<span class="st warn">有候选，还没选</span>'
            detail = "去「合成」页选一张"
        else:
            state = '<span class="st unknown">缺候选</span>'
            detail = "需要正式生成（Phase 4）"
        rows += f"<tr><td>{h(sid)}</td><td>{state}</td><td>{detail}</td></tr>"
    ready = bool(shots) and all(
        session.selection and session.selection.get("shot_id") == sid for sid in shots)
    body = [
        "<h2>交付包里有什么</h2>",
        _export_preview(session),
        '<p class="lead">导出不是「把图拷出去」：它要检查计划里的每一张都有选定成品，'
        "并且对最终文件重新跑一遍检查。</p>",
        _card("每一张的状态",
              f'<table class="grid"><tr><th>图</th><th>现在</th><th>还差什么</th></tr>'
              f"{rows}</table>",
              kind="ok" if ready else "warn",
              note="还差几张的时候不会被放行 —— 缺哪一张就说哪一张，"
                   "不用中间结果凑数。"),
        _card("包的结构",
              _ul(["<b>成品图</b>：每一张图只放最终挑中的那一份，而且必须先过复检",
                   "<b>清单</b>：每张图的来源、指纹、用了哪张参考图、过了哪些检查",
                   "<b>说明</b>：这是虚构演示商品、不用于真实上架，以及怎么自行核验"]),
              note="导出包里的东西能自己核验：换一台机器、换一个目录，照样能对得上。"),
        _card("导出前会重新跑什么",
              _ul(["最终文件的尺寸、长宽比、大小上限（按平台要求）",
                   "文件真的能打开、格式确实是要求的格式",
                   "计划里的每一张都有且只有一份成品"]),
              kind="warn",
              note="<b>离线演示，不写文件。</b>正式版这一步会真的落一个目录出来；"
                   "导出失败也不会撤销你已经做的选择。"),
    ]
    return layout("export", session, "".join(body), flash=flash)


# ------------------------------------------------------------------ 工作台
def _work_shot(session, shot_id: str) -> str:
    """工作台当前看哪一张：点的那张优先，否则看有候选的那张，再否则看第一张。"""
    shots = [sh["shot_id"] for sh in session.shots()]
    if shot_id in shots:
        return shot_id
    if session.candidate_shot in shots:
        return session.candidate_shot
    workable = [sid for sid in shots if session.candidates_of_shot(sid)]
    if workable:
        return workable[0]
    return shots[0] if shots else ""


def _work_cid(session, shot_id: str, cid: str) -> str:
    cids = session.candidates_of_shot(shot_id)
    if cid in cids:
        return cid
    return cids[0] if cids else ""


def page_workbench(session, *, flash: str = "", shot_id: str = "", cid: str = "") -> str:
    if session.blockers():
        return _blocked(session, "workbench")
    sid = _work_shot(session, shot_id)
    if not sid:
        return layout("workbench", session, "<h2>工作台</h2>"
                      '<p class="lead">方案里还没有图，先回任务页看看。</p>', flash=flash)
    sh = next(s for s in session.shots() if s["shot_id"] == sid)
    picker = " ".join(
        f'<a class="chip{" lock" if x == sid else ""}" href="/workbench?shot={h(x)}">'
        f"{h(x)}</a>" for x in [s["shot_id"] for s in session.shots()])
    sel = session.selection
    picked = (sel.get("candidate_id") if sel and sel.get("shot_id") == sid else "")
    cids = session.candidates_of_shot(sid)
    if picked:
        status = f"已选定 <b>{h(picked)}</b>"
    elif cids:
        status = "有候选，还没选"
    else:
        status = "还没有候选"
    plan = session.plan
    if session.plan_confirmed:
        confirm = ('<p class="st ok">已确认</p><p class="note">确认人：'
                   + h(plan.get("confirmed_by"))
                   + "。确认之后这份方案才有版本号，后面的提示词从它编译出来。</p>")
    else:
        confirm = ("<p>这是系统按事实卡与平台坑位给的<b>默认方案</b>："
                   "你不用自己写提示词，先看一遍，觉得可以就确认。</p>"
                   '<form method="post" action="/act">'
                   '<input type="hidden" name="op" value="confirm_plan">'
                   "<button>确认这个默认方案</button></form>"
                   '<p class="note">确认之前，它只是一份提案，不会进入下一步。'
                   "想手动调整也可以：正式版里每一张图的场景、构图和光线都能改，"
                   "改完仍然要过同样的事实检查。</p>")
    scheme = _card("这张图的默认方案",
        _kv([("它是干什么的", h(sh.get("purpose"))),
             ("场景", h(_lab(SCENE_LABEL, sh.get("scene_id")))
              + " · " + h(_lab(COMPOSITION_LABEL, sh.get("composition_id")))),
             ("可以变", h("、".join(_lab(VARIATION_LABEL, v)
                                   for v in (sh.get("allowed_variation") or [])))),
             ("必须保持一致", h("、".join(sh.get("must_preserve") or []))),
             ("看哪张参考图", h("、".join(_lab(VIEW_LABEL, v)
                                        for v in (sh.get("reference_views") or []))))])
        + confirm,
        kind="ok" if session.plan_confirmed else "")
    version = session.prompt(sid)
    if version is None:
        prompt_card = _card("提示词", "<p>这一张还没有编出提示词。</p>")
    else:
        locks = "".join(f'<span class="chip lock">{h(x)}</span>'
                        for x in version.get("locks_facts") or [])
        history = session.prompt_history.get(sid) or []
        hist_rows = "".join(
            f"<tr><td>{h((v.get('version_id') or '')[:12])}…</td>"
            f"<td>{h(v.get('origin'))}</td>"
            f"<td>{h((v.get('parent_version') or '—')[:12])}</td></tr>"
            for v in reversed(history))
        prompt_card = _card("实际会发给模型的那段话",
            f"<pre>{h(version.get('prompt_text'))}</pre>"
            f'<p>锁住的事实：</p><div class="chips">{locks}</div>',
            note="带锁的段落承载商品事实，编辑时不许删掉。") + _card(
            "不满意可以改",
            '<p>下面两种改法都会生成<b>新版本</b>，旧版本原样保留、可以对照。</p>'
            '<form method="post" action="/act">'
            '<input type="hidden" name="op" value="edit_prompt">'
            f'<input type="hidden" name="shot" value="{h(sid)}">'
            '<input type="hidden" name="mode" value="append">'
            '<p><label>加一句方向（推荐：只描述你想改的那一处）</label>'
            '<input type="text" name="text" placeholder="例如：背景更干净一些，商品保持在画面中央"></p>'
            "<button>按这句话改一版</button></form>"
            '<form method="post" action="/act">'
            '<input type="hidden" name="op" value="edit_prompt">'
            f'<input type="hidden" name="shot" value="{h(sid)}">'
            '<input type="hidden" name="mode" value="raw">'
            "<p><label>或者直接改全文</label>"
            f'<textarea name="text" spellcheck="false">{h(version.get("prompt_text"))}</textarea></p>'
            "<button class=\"ghost\">用这段全文替换</button>"
            '<p class="note">如果改完把带锁的段落删掉了，系统会拦下这次编辑，'
            "并告诉你删掉的是哪一段、它锁着哪几条事实。</p></form>") + _card(
            "版本记录",
            '<table class="grid"><tr><th>版本</th><th>怎么来的</th>'
            f"<th>上一版</th></tr>{hist_rows}</table>",
            note="编辑只产生新版本，不覆盖旧的；改动与结果绑定。")
    if not cids:
        cand_area = _card("候选", "<p>这一张还没有候选，需要正式生成"
                          "（离线演示不生成，所以这里暂时是空的）。</p>")
        rework_area = ""
    else:
        cur = _work_cid(session, sid, cid)
        cpick = " ".join(
            f'<a class="chip{" lock" if x == cur else ""}" '
            f'href="/workbench?shot={h(sid)}&cid={h(x)}">{h(x)}</a>' for x in cids)
        tech = session.technical.get(cur)
        fact = session.facts.get(cur)
        rev = session.reviews.get(cur) or {}
        checks = "".join(
            f"<tr><td>{h(_lab(CHECK_RULE_CN, c.get('rule')))}</td>"
            f"<td>{h(CHECK_VERDICT_CN.get(c.get('verdict'), c.get('verdict')))}</td></tr>"
            for c in ((tech.payload.get("checks") if tech else []) or []))
        fact_rows = "".join(
            f"<tr><td>{h(f.get('fact_id'))}</td>"
            f"<td>{h(FACT_VERDICT_CN.get(f.get('verdict'), f.get('verdict')))}</td>"
            f"<td>{h(_owner_label(f.get('responsible')))}</td></tr>"
            for f in ((fact.payload.get("facts") if fact else []) or []))
        unverified = (fact.payload.get("automated_routes_unverified_for") if fact else []) or []
        note = ("自动化路线在这几条上还没有校准，结论一律交人工："
                + h("、".join(unverified))) if unverified else "每条结论都写得出来是谁给的。"
        review = ""
        if rev:
            reasons = "".join(f'<span class="chip">{h(x)}</span>'
                              for x in (rev.get("reasons") or []))
            tone = "ok" if rev.get("verdict") == "keep" else "warn"
            review = (f'<p><span class="st {tone}">'
                      + h(VISUAL_VERDICT_CN.get(rev.get("verdict"), rev.get("verdict")))
                      + "</span>" + h(_lab(REVIEWER_CN, rev.get("reviewer"))) + "</p>"
                      + f'<div class="chips">{reasons}</div>'
                      + f'<p class="note">{h(rev.get("notes"))}</p>')
        ok = OFF.selectability(session, cur)
        if ok["ok"]:
            choose = "<button>选它作为成品</button>"
        else:
            choose = ('<button disabled>还不能选</button>'
                      f'<span class="why">{h(ok["why"])}</span>')
        cand_area = _card("怎么读这三关",
            _ul(["<b>商品长得对不对</b>：拿事实卡逐条比。判不了的不会被写成通过，"
                 "而是写明「还判不了」，并指到人工那一栏。",
                 "<b>谁给的结论</b>：机器按尺子量出来的、模型报的风险、"
                 "还是人逐张确认的，这里分得很清楚。",
                 "<b>好不好看</b>：由人给「可以留 / 要重做 / 不要」，并写明理由；"
                 "系统不把审美算成一个分数。"])) + (
            f'<div class="cand"><div class="chips">{cpick}</div>'
            f'<img src="/img?c={h(cur)}" alt="{h(cur)}">'
            f"<h4>{h(cur)}</h4>"
            + _card("图片本身合不合格", f'<table class="grid">{checks}</table>')
            + _card("商品长得对不对",
                    '<table class="grid"><tr><th>事实</th><th>结论</th>'
                    f"<th>谁给的结论</th></tr>{fact_rows}</table>", note=note)
            + _card("好不好看（人给的）",
                    review or '<p class="why">还没有人工结论</p>',
                    note="审美只给可指认的理由，不给分数。")
            + _card("选定",
                    '<form method="post" action="/act">'
                    '<input type="hidden" name="op" value="select">'
                    f'<input type="hidden" name="c" value="{h(cur)}">{choose}</form>'
                    '<p class="note">生成不等于选定：选是决定，单独记一笔。</p>',
                    kind="ok" if picked == cur else "")
            + "</div>")
        codes = OFF.reason_codes()
        options = "".join(
            f'<option value="{h(c["code"])}">{h(REASON_CN.get(c["code"], c["code"]))}</option>'
            for c in codes)
        rule_rows = "".join(
            f'<tr><td>{h(REASON_CN.get(c["code"], c["code"]))}</td>'
            f'<td>{h(c["label"])}</td>'
            f'<td>{h("、".join(OFF.reason_route(c["category"])["changes"]) or "——")}</td></tr>'
            for c in codes)
        rework_area = _card("不满意，说哪里",
            '<form method="post" action="/act">'
            '<input type="hidden" name="op" value="rework">'
            f'<input type="hidden" name="shot" value="{h(sid)}">'
            f'<p><label>这一张（<b>{h(sid)}</b>）哪里不满意：</label> '
            f'<select name="reason">{options}</select> '
            '<button>看系统会改什么</button></p></form>'
            '<p class="note"><b>离线演示，不产生新候选。</b>'
            "这一步只算路由，不动任何图；新版候选进来后，旧版原样保留。</p>") + _card(
            "刚才选的那一次", _rework_result(session),
            kind="ok" if (session.rework or {}).get("outcome") == "accepted" else "") + _card(
            "原因与「只改这些」的对照表",
            '<table class="grid"><tr><th>原因</th><th>归到哪一类</th>'
            f"<th>只改这些</th></tr>{rule_rows}</table>",
            note="原因归不了类时会交人工，不做无界自动重试。")
    if picked:
        reviewers = "、".join(sorted(set(
            _lab(OWNER_CN, r) for r in (sel.get("fact_responsible") or []))))
        rv = sel.get("visual_review") or {}
        rules = session.rules or {}
        spec = _kv([("输出尺寸", f'{h(rules.get("long_side_px"))} 像素（长边），长宽比 '
                                f'{h(rules.get("aspect_ratio"))}'),
                    ("文件格式", h(rules.get("export_format"))),
                    ("文件大小上限", f'{h(rules.get("max_file_mb"))} MB'),
                    ("命名规则", h(rules.get("filename_pattern") or "未定"))])
        copy_texts = OFF.copy_records(session)
        if copy_texts:
            words = "、".join(str((c or {}).get("text") or "") for c in copy_texts)
            compose_note = ('<p class="why">这一张的方案里有<b>要叠上去的文案</b>（'
                            + h(words) + "）。精确文字由排版层完成，而这一版不做排版 —— "
                            "所以「叠上文案之后的成品」现在是<b>未知</b>：不猜它成功，"
                            "也不把它算成已经交付。</p>")
        else:
            compose_note = ("<p>方案里没有任何要叠上去的文案，所以成品是<b>原样输出</b>："
                            "像素与容器格式都不变，这一步也会留下记录，"
                            "不因为「什么都没做」就跳过。</p>")
        done_area = _card("选中的成品",
            f'<div class="grid2"><div><img src="/img?c={h(picked)}" alt="{h(picked)}" '
            'style="width:100%;border-radius:8px"></div><div>'
            + _kv([("事实结论由谁给", h(reviewers) or "—"),
                   ("人的审美判定", h(VISUAL_VERDICT_CN.get(rv.get("verdict"),
                                                           rv.get("verdict")))),
                   ("选的人", h(_lab(SELECTED_BY_CN, sel.get("selected_by"))))])
            + "</div></div>" + spec + compose_note,
            kind="ok",
            note="「可以留」和「被选中」是两件事：留是评价，选是决定，决定单独记一笔。")
    else:
        done_area = ""
    body = [
        f"<h2>{h(sid)} 工作台</h2>",
        f'<p class="lead">{h(sh.get("purpose"))}。当前状态：<b>{status}</b>。</p>',
        f'<div class="chips">{picker}</div>',
        scheme,
        prompt_card,
        cand_area,
        rework_area,
        done_area,
    ]
    return layout("workbench", session, "".join(body), flash=flash)


def _export_preview(session) -> str:
    """导出页顶部的预览：能交付的部分先摆出来，缺的图明说，按钮锁死。"""
    shots = [sh["shot_id"] for sh in session.shots()]
    sel = session.selection
    rows = ""
    missing = []
    for sid in shots:
        if sel and sel.get("shot_id") == sid:
            rows += (f"<tr><td>{h(sid)}</td><td>已选定 "
                     f"{h(sel.get('candidate_id'))}</td>"
                     f'<td><a href="/workbench?shot={h(sid)}">去工作台看</a></td></tr>')
        elif session.candidates_of_shot(sid):
            missing.append(sid)
            rows += (f"<tr><td>{h(sid)}</td><td>有候选，还没选</td>"
                     f'<td><a href="/workbench?shot={h(sid)}">去选一张</a></td></tr>')
        else:
            missing.append(sid)
            rows += (f"<tr><td>{h(sid)}</td><td>缺候选</td>"
                     "<td>需要正式生成（离线演示不生成）</td></tr>")
    if missing:
        action = (f'<button disabled>现在不能提：还缺 '
                  f'{h("、".join(missing))}（演示也不写文件）</button>'
                  '<p class="note">按钮长在这里就是为了让你看到终点：'
                  "缺的图补上之后，这里才会变成真的导出。</p>")
    else:
        action = ('<button disabled>演示不写文件：正式版这里会真的落一个目录出来</button>'
                  '<p class="note">离线演示只预览，不写文件。</p>')
    return _card("先看一眼能交付的部分",
                 f'<table class="grid"><tr><th>图</th><th>现在</th><th>去哪</th></tr>'
                 f"{rows}</table>{action}",
                 kind="" if missing else "ok")
def render_all(session) -> dict:
    """依次渲染八页：离线自检用，也是"每一页都取得到数据"这条判据的落点。"""
    out = {}
    for path, _label, _title in PAGES:
        out[path] = page_for(path, session)
    return out


def page_for(path: str, session, query: dict | None = None, *, flash: str = "") -> str:
    query = query or {}
    if path == "":
        return page_home(session, flash=flash)
    if path == "task":
        return page_task(session, flash=flash)
    if path == "workbench":
        return page_workbench(session, flash=flash, shot_id=query.get("shot", ""), cid=query.get("cid", ""))
    if path == "export":
        return page_export(session, flash=flash)
    raise KeyError(path)
