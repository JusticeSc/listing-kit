r"""编排器：表 → 齐套 → 扇出 → 日志。整条链路**唯一的分派点**。

它做五件事
----------
    1. 读表 —— 并且**启动即校验**（表错了在跑之前炸，不要白烧调用费）
    2. 算这次做哪几张 —— 齐套判定（张数是算出来的，不是配置项）
    3. 产出**唯一那份主体** `subject.png`（不变量 A，见 src/subject.py）
    4. 把渲染器声明的、**要求先抠好**的素材提前抠出来（见 src/cutouts.py）
    5. 对每个坑位调 `registry.get(slot["renderer"])(slot, ctx)`
       —— 拿回来的产物**逐张校验**并落进 run.jsonl（validators.validate）

第 3、4 步刻意放在这里而不是放进渲染器：一旦每个渲染器自己抠图，系统里就有
七个"主体"，位置 1 与位置 2 的轮廓可能不一致，"成套"这件事就没了保证。

**抠图全部发生在模型调用之前**，这条顺序有两个理由，第二个是实测出来的：
    · 抠图失败就不该再烧调用费（这条规矩本来就在主体那一步写着）；
    · 抠图推理会偶发抓不到内存（ORT bad allocation / numpy MemoryError），
      同一个调用在进程刚起来时稳、跑完一次 55s 的云端生成之后就不稳。
      位置 6/7 的抠图原先就在后半段，实测整格失败过。
    顺带的好处：抠好的素材一轮只抠一次，于是只动位置的重做不必重抠一遍。

它**不做**的事（那些是渲染器自己的事）
------------------------------------
    · 不判断"这个坑位该怎么画"      · 不拼提示词
    · 不管底色取什么色              · 不管叠字怎么排

铁律：**本文件里不允许出现按坑位号分支的判断。**
    一旦出现，就说明坑位行为又回到了代码里，"加一个坑位 = 加一行数据"立刻失效。
    验证方式（M1 验收②，每次改动后跑，**必须零输出**）：
        grep -En 'slot\["id"\] ==|slot\.id ==' src/orchestrator.py   → 必须无输出

两条时间轴（这是刻意的拆分）
--------------------------
    plan_run()  只算，不产任何文件、不调任何模型（--dry-run 走这条）
    execute()   真跑，落 run.jsonl 与产物

分开是为了让"这次会出几张、调几次模型"能在**零副作用**的前提下被检查。
plan 自带 export / catalog，所以 execute 不需要再读一次盘，也不需要全局缓存。
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

import assets as assets_mod
import cutouts as cutouts_mod
import fixers
import intake
import registry
import schema
import subject as subject_mod
import textlayer
import validators
from kit_config import ROOT, load_brand
from planner import extract_facts


def _jsonable(obj):
    """把渲染器报告压成可 JSON 落盘的形式（不可序列化的转成字符串）。

    为什么必须落盘：`run.jsonl` 是**唯一**能回溯"这一张当时是怎么产出来的"的地方。
    少了它，M3 验收里"位置 1/2/3 的产品像素同源"就只能靠目测 ——
    而目测不是断言（tools/verify_m3.py 读的就是这里写下的 paste_box）。
    """
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def _log(fh, stage: str, **kw) -> None:
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "stage": stage}
    rec.update(kw)
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    fh.flush()


@dataclass
class ProductPackage:
    """一个商品包读进来之后的三样东西。

    为什么要包成一个对象：路径解析的**唯一**实现（load_product）需要同时给出
    解析后的 product、素材基准目录、以及包本身的位置 —— 第三个是给
    plan.json 记"这一轮是拿哪个包跑的"用的（消费方：审核台的重做，
    它必须能凭一条已存在的 run 重新加载输入，否则界面上点重做会缺 product）。
    """
    product: dict
    base_dir: Path
    path: Path


def load_product(product_path: str | Path) -> ProductPackage:
    """读商品包，并把素材相对路径解析成绝对路径。

    为什么这件事必须只有一处实现：**素材路径按谁解析**是一个答案唯一的问题。
    调用方有两个 —— run.py（CLI）与 web/server.py（审核台）—— 如果各写一遍，
    迟早出现"命令行跑得出图、审核台跑不出图"这种最难查的分歧。
    （平铺 images[] 的相对路径同样按输入文件所在目录解析，属过渡期兼容。）

    注意 base_dir 是**输入文件所在目录**而不是进程 cwd：运营把商品包与图片放在
    同一个文件夹里，从哪儿启动程序都不该改变结果。
    """
    p = Path(product_path).resolve()
    product = json.loads(p.read_text(encoding="utf-8"))
    base = p.parent
    imgs = []
    for v in product.get("images") or []:
        q = Path(v)
        imgs.append(str(q if q.is_absolute() else (base / q)))
    product["images"] = imgs
    return ProductPackage(product=product, base_dir=base, path=p)


@dataclass
class SlotDecision:
    """一个坑位这一次的处置结论。dry-run 打印的就是它。"""
    slot_id: int
    role: str
    purpose: str
    renderer: str
    text: str
    background: str
    status: str                 # will_run | skipped
    missing: list[str] = field(default_factory=list)
    pixels_from: str = ""

    @property
    def calls_model(self) -> bool:
        return registry.calls_model(self.renderer)


@dataclass
class RunPlan:
    upc: str
    out_dir: Path
    run_dir: Path
    stamp: str
    table_total: int
    decisions: list[SlotDecision]
    doable: list[dict]
    skipped: list[dict]
    facts: dict
    supplied: dict
    broken: dict
    model_calls: int
    export: dict
    catalog: dict
    e0: "intake.E0Report | None" = None
    needs_font: bool = False
    needs_competitor: bool = False
    rejected: str | None = None
    # 这一轮是拿哪个商品包跑的。消费方：plan.json → run_state → 审核台的重做
    #   （重做需要重新加载输入；界面上不该要求人再选一次商品包）。
    product_path: str = ""

    @property
    def will_run(self) -> int:
        return sum(1 for d in self.decisions if d.status == "will_run")

    @property
    def needs_subject(self) -> bool:
        """本次要不要产出 subject.png。

        两个消费方（所以它不是一个白算的属性）：
            orchestrator.execute —— 决定跑不跑抠图
            run.py               —— 干跑时告诉人"真跑会先做一次本地抠图"
        判据由 src/subject.py 定义，这里只是转达 —— 判定规则只有一份。
        """
        return subject_mod.needs_subject(self.doable)

    @property
    def cut_kinds(self) -> list[str]:
        """本次要**提前抠好**的素材名（按坑位顺序去重，确定性输出）。

        判据是渲染器声明的 `cuts`（registry.cuts_of），不是坑位号、也不是
        渲染器名 —— 那样编排器就又知道"谁是谁"了。加一个要抠素材的坑位，
        只是它那个文件多声明一个 `cuts=("xxx",)`，这里不用改。

        顺序取"首次出现"而不是字典序：它决定抠图产物在 raw/ 里的落盘次序，
        而那个次序会被日志与耗时记录反映出来 —— 与表里的坑位顺序一致更好读。
        """
        seen: list[str] = []
        for s in self.doable:
            for k in registry.cuts_of(s["renderer"]):
                if k in self.supplied and k not in seen:
                    seen.append(k)
        return seen

    def summary_line(self) -> str:
        return (f"表内 {self.table_total} · 齐套可做 {len(self.doable)} · "
                f"本次生成 {self.will_run} · 模型调用 {self.model_calls}")


# ---------------------------------------------------------------- plan

def _slot_plan(slot: dict, facts: dict) -> dict:
    """把一个坑位 + 事实，压成一条可重放的执行计划。

    plan 是整条链路唯一的状态，其余产物都是它的确定性映射；单张重做 = 重放其中一条。
    注意这里**按 needs 选文字来源，而不是按坑位号**：
        需要 specs 的坑位 → 文字来自规格表；其余 → 来自卖点列表。
    于是加一个"参数对照图"不需要改这段代码。
    """
    needs = slot.get("needs") or []
    text = slot.get("text")
    callouts: list[str] = []
    if text != "none":
        limit = int(slot.get("max_callouts") or 0)
        if "specs" in needs and facts.get("specs"):
            callouts = [f"{k}：{v}" for k, v in list(facts["specs"].items())][:limit]
        else:
            callouts = list(facts.get("bullets") or [])[:limit]

    return {
        "slot_id": slot["id"],
        "role": slot.get("role"),
        "purpose": slot.get("purpose"),
        "renderer": slot["renderer"],
        "text": text,
        "background": slot.get("background"),
        # mandatory 进 plan 是给审核台用的：界面上"平台强制项不可关"这条必须由
        # 表里的字段推出，不能在界面里再写一份"位置 1 是强制的"。
        "mandatory": bool(slot.get("mandatory")),
        "subject": facts.get("subject"),
        "callouts": callouts,
        "specs": facts.get("specs") if "specs" in needs else {},
        "needs": needs,
        "validate_level": slot.get("validate_level"),
        "validate_rules": slot.get("validate_rules") or [],
    }


def plan_run(product: dict, *, only: list[int] | None = None,
             out_dir: str | Path = "out", slots_path: str | Path | None = None,
             base_dir: str | Path | None = None,
             product_path: str | Path | None = None) -> RunPlan:
    """算这一次怎么跑。**不写任何文件、不调任何模型。**"""
    cfg = schema.assert_valid(slots_path)          # 表错了在这里就炸
    brand = load_brand()
    catalog = yaml.safe_load(
        (ROOT / cfg["catalog"]).read_text(encoding="utf-8")) or {}

    slots = list(cfg["slots"])
    if only:
        slots = [s for s in slots if s["id"] in only]

    upc = product.get("upc") or "NOUPC"
    base = Path(base_dir) if base_dir else Path(".")
    supplied, broken = assets_mod.big_picture_facts(product, base)
    facts = extract_facts(product, brand)

    # ---- 先算齐套（这次做哪几张），再体检。
    #
    # ★ 顺序不是随意的：E0 的**条件签字项**（字体授权 / 竞品图干净）必须只针对
    #   "这一轮真的会出图的坑位"要求。表里写着位置 7、而这次没给竞品图 → 位置 7
    #   会被跳过 → 就不该要求"竞品图干净"这条签字。要判这件事，只有先算齐套。
    #   （同理，"一张素材都不缺但都不会用到"也不该触发图片类签字。）
    doable, skipped = assets_mod.resolve(slots, supplied)

    # 为什么从 doable 而不是 slots 算：`--only 1` 这种过滤之后，
    # 表里其余坑位这次根本不参与，不该因为字体缺失而误拒。
    needs_font = any((s.get("text") or "none") != "none" for s in doable)
    needs_competitor = any("competitor" in (s.get("needs") or []) for s in doable)

    # ---- E0 体检：在抠图之前、在任何模型调用之前。
    #      它只对 supplied 里的图片负责 —— 没提供的素材属于"跳过"，不属"体检"。
    e0 = intake.run_e0(supplied=supplied, product=product,
                       export=cfg["export"], brand=brand,
                       needs_font=needs_font, needs_competitor=needs_competitor)

    # 拒收理由合并到一处（run.py 只认 rejected 这一条路径，返回码 3）
    reasons: list[str] = list(e0.rejects)
    try:
        assets_mod.require_subject(supplied, [s for s in slots if s.get("mandatory")])
    except assets_mod.Rejected as exc:
        reasons.append(str(exc))
    rejected: str | None = "；".join(reasons) if reasons else None

    if rejected:
        # 整批拒绝：所有坑位都不做，但**逐条列出来**，让人看见拒的是哪一条。
        doable, skipped = [], []
        decisions = [
            SlotDecision(s["id"], s.get("role", ""), s.get("purpose", ""),
                         s["renderer"], s.get("text", ""), s.get("background", ""),
                         "skipped", missing=list(s.get("needs") or []),
                         pixels_from=registry.summary_of(s["renderer"]))
            for s in slots
        ]
    else:
        # doable / skipped 已在上面算过（E0 需要先知道它们）—— 不重复调用 resolve：
        # 算两遍不会出错，但会让"哪一次的结果是真的"变成一个需要读代码才能回答的问题。
        skip_index = {k["slot_id"]: k for k in skipped}
        decisions = [
            SlotDecision(
                s["id"], s.get("role", ""), s.get("purpose", ""), s["renderer"],
                s.get("text", ""), s.get("background", ""),
                "skipped" if s["id"] in skip_index else "will_run",
                missing=list(skip_index[s["id"]]["missing"]) if s["id"] in skip_index else [],
                pixels_from=registry.summary_of(s["renderer"]),
            )
            for s in slots
        ]

    # 唯一性：同一 UPC 并发运行会撞名，后果是**静默**的（日志被截断、图被覆盖、
    # 校验却全 PASS）。用微秒而非 pid：跨进程撞名概率为零。
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return RunPlan(
        upc=upc, out_dir=Path(out_dir), run_dir=Path(out_dir) / f"{upc}_{stamp}",
        stamp=stamp, table_total=len(slots), decisions=decisions,
        doable=doable, skipped=skipped, facts=facts, supplied=supplied,
        broken=broken, export=cfg["export"], catalog=catalog,
        model_calls=sum(1 for s in doable if registry.calls_model(s["renderer"])),
        e0=e0, needs_font=needs_font, needs_competitor=needs_competitor,
        rejected=rejected,
        product_path=str(product_path) if product_path else "",
    )


# ---------------------------------------------------------------- 素材抠图产出

def produce_cutouts(kinds: list[str], supplied: dict, run_dir: Path, *,
                    cutout_mode: str | None = None, fh=None,
                    progress=None) -> tuple[dict, dict]:
    """把这一轮要用的素材**提前抠好**，一份一个产物。返回 (成功的, 失败的)。

    为什么这个过程是"产出"而不是"渲染器内部的事"：与 `subject.prepare` 同理 ——
    一旦让每个渲染器在用的时候自己抠，同一件事就有两处实现、两种时序、
    两份日志口径。集中之后，抠图在整条链路上只有**一个时刻**（模型调用之前），
    于是"抠图失败不烧调用费"这条规矩对所有素材都成立。

    失败**不抛**：一样素材抠不出来，不该让另外六张也出不来。
    调用方把失败的素材名变成"跳过要它的那些坑位"（复用齐套判定的语义）。
    """
    good: dict[str, dict] = {}
    bad: dict[str, str] = {}
    for kind in kinds:
        if progress:
            progress(f"素材产出  抠 {kind}（本地，不联网、零 API 成本）…")
        t = time.time()
        try:
            info = cutouts_mod.prepare(kind, supplied[kind], run_dir,
                                       cutout_mode=cutout_mode)
        except Exception as exc:                      # noqa: BLE001 见 docstring
            bad[kind] = str(exc)[:300]
            if fh:
                _log(fh, "cutout_error", kind=kind, source=supplied.get(kind),
                     error=bad[kind])
            continue
        good[kind] = info
        if fh:
            _log(fh, "cutout", kind=kind, path=info["path"], sha256=info["sha256"],
                 size=info["size"], source=info["source"],
                 mode=(info.get("cutout") or {}).get("mode"),
                 alpha_coverage=info["alpha_coverage"],
                 # 抠图是**本地**推理（不联网、不计入 model_calls），但有实打实的
                 # 耗时。记在它自己这一条上，才是"让成本落在产生它的那一步"。
                 elapsed_s=round(time.time() - t, 3))
        if progress:
            progress(f"        ✓ {kind} {round(time.time() - t, 1)}s → "
                     f"{Path(info['path']).name}")
    return good, bad


# ---------------------------------------------------------------- execute

def execute(p: RunPlan, *, dry_run: bool = False,
            text_override: str | None = None,
            cutout: str | None = None,
            model: str | None = None,
            autofix: bool = False,
            progress=None) -> dict:
    """按 plan 真跑。dry_run=True 时只把计划还回去，不落任何文件。

    text_override / cutout / model 都是**执行期**参数（不进 plan）：plan 描述
    "做哪几张、每张什么形状"，而"这一轮用哪种抠图、哪个生成模型"不改变计划本身。
    让它们留在 plan 外，也让 dry-run 的零副作用更容易保证。

    model 到 M4 才有消费方（位置 4 是全链路唯一调云端生成模型的一格）——
    在此之前加它就是个死参数。它只影响**位置 4**；其余六个坑位由声明保证零模型，
    传进来的值对它们没有任何作用。

    progress 是一个回调（收一行字符串）。它存在的理由很具体：位置 4 要调模型，
    约 75s 一张 —— 那 75s 里如果什么都不打印，人就不知道是在跑还是卡住了。
    **等待期的可见性不是装饰**，它是"人在回路里"能不能成立的前提。
    """
    if p.rejected:
        return {"ok": False, "rejected": p.rejected, "results": [], "plan": p}
    if dry_run:
        return {"ok": True, "dry_run": True, "results": [], "plan": p}

    # ★ 人工签字门禁：**只在真跑时拦**。
    #   干跑不产任何成品图，所以允许它在未签字状态下运行 ——
    #   干跑的作用恰恰是告诉你"还差哪几条没签"。
    #   这也让"工具判不了的东西"在两条路径上有一致的表现：
    #     自动项（尺寸/可读性）→ 拒收，dry-run 也拒
    #     人工项（水印/道具…）  → 真跑拒收，dry-run 只列出来给你看
    if p.e0 and p.e0.attest_missing:
        missing = list(p.e0.attest_missing)
        return {
            "ok": False, "unattested": missing, "results": [], "plan": p,
            "message": (
                f"素材合规未签字：{'、'.join(missing)} —— 这几项工具判不了"
                f"（见 src/intake.py 的说明），必须在 product 的 "
                f"attest.confirmed 里逐条确认后才允许出图。干跑不受此限。"),
        }

    p.run_dir.mkdir(parents=True, exist_ok=True)
    (p.run_dir / "raw").mkdir(exist_ok=True)

    slot_plans = [_slot_plan(s, p.facts) for s in p.doable]
    if text_override:
        # 覆盖只对 text != none 的坑位生效（平台强制坑位恒为 none）。
        # ★ 校验规则必须跟着改 —— 否则会出现"这一轮不出字、却仍要求验文字"，
        #   那是自相矛盾的配置，只会产出一致性错误的校验结论。
        for sp in slot_plans:
            if sp["text"] == "none":
                continue
            sp["text"] = text_override
            rules = list(sp.get("validate_rules") or [])
            if text_override == "none":
                rules = [r for r in rules if r != "text_present"]
                sp["callouts"] = []
            elif "text_present" not in rules:
                rules.append("text_present")
            sp["validate_rules"] = rules

    (p.run_dir / "plan.json").write_text(json.dumps({
        "upc": p.upc, "stamp": p.stamp, "facts": p.facts,
        "supplied": p.supplied, "broken": p.broken,
        # 记下输入包的位置：重做要凭它重新加载当次输入（改了卖点文案再重排文字层，
        # 读的就该是改过之后的那份），审核台的"重做"按钮也靠它。见 RunPlan.product_path。
        "product": p.product_path or None,
        # E0 结论与签字一起落盘：**"谁在什么时候确认过什么"是可回溯的**，
        # 这是人工项唯一能被事后审计的方式（工具本身验不了它们）。
        "e0": ({"images": p.e0.images, "notices": p.e0.notices,
                "attest": p.e0.attest, "font": p.e0.font} if p.e0 else None),
        "slots": slot_plans,
        # ---- 以下三项的消费方是 orchestrator.run_state（审核台的读模型）
        #      —— 它们是"这一轮的计划"，不是"这一轮的经过"（经过在 run.jsonl）。
        #   跳过清单：审核台要能显示缺料的那几格，否则"七张"会显得凭空少了三张
        #   声明调用数：成本条要能说"这次本来要调几次模型"
        #   该签未签：签字状态现在只在真跑时拦人，审核台看得到才谈得上"先补签"
        "skipped": p.skipped,
        "model_calls": p.model_calls,
        "attest_missing": list((p.e0.attest_missing if p.e0 else []) or []),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    ctx = {
        "upc": p.upc, "stamp": p.stamp, "run_dir": str(p.run_dir),
        "out_dir": str(p.out_dir), "export": p.export, "catalog": p.catalog,
        "brand": load_brand(), "facts": p.facts, "supplied": p.supplied, "seq": 1,
        "subject": None,       # 由下面的「主体产出」步骤填充（见 src/subject.py）
        "cutouts": {},         # 由下面的「素材产出」步骤填充（见 src/cutouts.py）
        "model": model,        # 仅位置 4 消费（其余六格声明零模型）
        # 抠图方式：主体、内容物、竞品三处都读它。**一个开关管三处** ——
        # 只对主体生效的开关在 rembg 不稳的机器上等于没有退路。
        "cutout_mode": cutout,
    }

    results: list[dict] = []
    with (p.run_dir / "run.jsonl").open("w", encoding="utf-8") as fh:
        _log(fh, "run_start", upc=p.upc, table=p.table_total, product=p.product_path or None,
             doable=[s["id"] for s in p.doable],
             skipped=p.skipped, model_calls=p.model_calls)
        if p.e0:
            _log(fh, "e0_intake",
                 images={k: {"long_side": v.get("long_side"),
                             "mode": v.get("mode"),
                             "has_alpha": v.get("has_alpha"),
                             "corner_white": v.get("corner_white")}
                         for k, v in p.e0.images.items()},
                 notices=p.e0.notices,
                 attest_by=(p.e0.attest or {}).get("by"),
                 attest_date=(p.e0.attest or {}).get("date"),
                 attest_confirmed=sorted((p.e0.attest or {}).get("confirmed") or []),
                 font=(p.e0.font or {}).get("path"))

        # ★ 主体只有一份（不变量 A）：在这里产出**一次**，之后所有渲染器共享它。
        #   为什么放在模型调用之前：抠图失败了就别去烧调用费。
        #   注意它是**本地**抠图（见 src/subject.py），不联网、不计入 model_calls ——
        #   registry 里的 calls_model 指的是云端生成模型（位置 4 那一格）。
        if p.needs_subject:
            if progress:
                progress("主体产出  本地抠图一次（不联网、零 API 成本）…")
            t_sub = time.time()
            try:
                info = subject_mod.prepare(p.supplied["front"], p.run_dir,
                                           cutout_mode=cutout)
            except subject_mod.SubjectError as exc:
                # 抠图失败属**输入问题**，工具修不了 → 整批停下、给出下一步。
                # 绝不拿着"抠图没生效"的主体继续产出：那种图四周留白是合成上去的
                # 白画布，位置 1 的白底校验会全过，产品区里却仍是原照片的背景。
                _log(fh, "subject_error", error=str(exc))
                return {"ok": False, "subject_error": str(exc),
                        "results": [], "plan": p}
            ctx["subject"] = info
            _log(fh, "subject", path=info["path"], sha256=info["sha256"],
                 size=info["size"], source=info["source"],
                 # 键名与 cutout 记录一致（都叫 mode）：stage 已经说明了是哪一样，
                 # 再给同一个事实起两个名字，读数的人就得记住两张表。
                 mode=(info.get("cutout") or {}).get("mode"),
                 alpha_coverage=info["alpha_coverage"],
                 # 抠图是**本地**推理（不联网、不计入 model_calls），但它有实打实的
                 # 耗时（实测 10—15s）。记下来，免得它被误算到后面某个渲染器头上。
                 elapsed_s=round(time.time() - t_sub, 3))

        # ★ 素材抠图产出（内容物 / 竞品）：**提前、集中、一轮一次**。
        #   为什么必须在这一步（而不是渲染器用的时候自己抠）—— 见
        #   registry.register 的 cuts 说明与 src/cutouts.py 的模块头。
        #   一句话：它让三处抠图都发生在模型调用之前（进程最清爽的时候），
        #   让抠图失败在花钱之前暴露，并且让重做不必重抠。
        cut_good, cut_bad = produce_cutouts(
            p.cut_kinds, p.supplied, p.run_dir, cutout_mode=cutout,
            fh=fh, progress=progress)
        ctx["cutouts"] = cut_good

        # 抠不出来的素材 → **跳过要它的坑位**，而不是整批停、更不是照跑。
        #   复用齐套判定那一套语义（"缺料就跳过、不凑"），只是这次"缺"是
        #   跑出来才知道的。plan.json 里的计划不动（计划就是计划），
        #   实情记进 run.jsonl 与 p.skipped（run.py 的"已跳过"计数才诚实）。
        work = list(zip(p.doable, slot_plans))
        if cut_bad:
            kept = []
            for slot, sp in work:
                hit = [k for k in (slot.get("needs") or []) if k in cut_bad]
                if not hit:
                    kept.append((slot, sp))
                    continue
                why = f"素材抠图失败（{'、'.join(hit)}）：{cut_bad[hit[0]]}"
                # cause 与 assets.py 那侧同构（见那里的注释）：这一条是**运行时**跳过，
                # 不是「入口就缺料」。两者对运营的含义完全相反 ——
                # 缺料要去补素材照片，抠图失败要关掉审核台/降并发后重跑。
                # `logged` 标记它已经在这里落过一次日志，收尾时不再重复记（见 run_end 之前）。
                p.skipped.append({"slot_id": slot["id"], "missing": hit,
                                  "cause": "cutout_error", "logged": True,
                                  "reason": why})
                _log(fh, "slot_skipped", slot_id=slot["id"], missing=hit,
                     cause="cutout_error", reason=why)
                if progress:
                    progress(f"        × 跳过位置 {slot['id']} —— {why[:70]}")
            work = kept

        for i, (slot, sp) in enumerate(work, 1):
            t0 = time.time()
            if progress:
                progress(f"[{i}/{len(work)}] 位置 {slot['id']} "
                         f"{slot.get('purpose')} → {slot['renderer']}")
            try:
                # ★ 唯二分派点：名字 → 函数。这里没有、也不允许有 if slot id
                art = registry.get(slot["renderer"])(slot, {**ctx, "plan": sp})
            except Exception as exc:      # 单张失败不拖垮整批（"单张重做"的前提）
                _log(fh, "render_error", slot_id=slot["id"], error=str(exc)[:300])
                results.append({"slot_id": slot["id"], "ok": False,
                                "error": str(exc)[:300]})
                continue

            detail = _jsonable({k: v for k, v in art.items() if k != "path"})
            # 耗时落 JSONL，而不只是打印：M3 验收③要证的是"改文案重出很便宜"，
            # 那需要一份**能被脚本断言**的耗时证据，而不是一句"看着挺快"。
            # 口径 = 渲染调用本身（不含主体抠图与校验），因为"重出"省掉的正是它。
            elapsed_s = round(time.time() - t0, 3)
            _log(fh, "render", slot_id=slot["id"], renderer=slot["renderer"],
                 path=art.get("path"), placeholder=bool(art.get("placeholder")),
                 elapsed_s=elapsed_s, detail=detail)
            if progress:
                mark = "（占位图）" if art.get("placeholder") else ""
                progress(f"        ✓ {elapsed_s}s {mark} "
                         f"{Path(str(art.get('path') or '')).name}")

            # ★ 校验：按**生效的**规则跑（sp 里带着 --text-mode 调整过的规则）。
            #   若读 slot["validate_rules"]，`--text-mode none` 就会仍然要求验文字，
            #   产出一个"这轮没出字、却报文字缺失"的自相矛盾结论。
            eff_slot = {**slot, "validate_rules": sp.get("validate_rules")}
            verdict = validators.validate(art["path"], eff_slot, p.export, p.upc)
            _log(fh, "validate", slot_id=slot["id"], passed=verdict["passed"],
                 failed=verdict["failed"],
                 checks=[{"name": c["name"], "ok": c["ok"]}
                         for c in verdict["checks"]])

            # ★ L0 确定性修复（**显式开关，默认关**，见 fixers 模块头）。
            #   为什么默认关：它**改像素**。默认开启会让"这一轮的产物到底是不是
            #   渲染器直接产出的"变成一个要读日志才知道的问题 —— 而那正是本项目
            #   一贯拒绝的那种不透明（参考库的 check_listing.py --fix 同样
            #   是显式参数，不是默认行为）。
            fix_info = None
            if autofix and not verdict["passed"]:
                fixrep = fixers.repair(art["path"], eff_slot, p.export, p.upc)
                fix_info = {
                    "changed": fixrep["changed"],
                    "attempts": fixrep["attempts"],
                    "escalate": fixrep["escalate"],
                    "remaining": fixrep["remaining"],
                    "passed_before": fixrep["verdict_before"]["passed"],
                    "passed_after": fixrep["verdict_after"]["passed"],
                    "sha256_before": fixrep["sha256_before"],
                    "sha256_after": fixrep["sha256_after"],
                }
                _log(fh, "autofix", slot_id=slot["id"], changed=fixrep["changed"],
                     attempts=[{k: a.get(k) for k in
                                ("check", "rung", "fixed", "action", "reason",
                                 "before", "after")}
                               for a in fixrep["attempts"]],
                     passed_before=fixrep["verdict_before"]["passed"],
                     failed_before=fixrep["verdict_before"]["failed"],
                     passed_after=fixrep["verdict_after"]["passed"],
                     failed_after=fixrep["verdict_after"]["failed"],
                     remaining=fixrep["remaining"], escalate=fixrep["escalate"],
                     sha256_before=fixrep["sha256_before"][:16],
                     sha256_after=fixrep["sha256_after"][:16])
                verdict = fixrep["verdict_after"]
                # 复验结论**必须再写一条 validate**：run_state 取的是最后一条
                #   validate（见 run_state 的说明）。不写它，审核台显示的仍是
                #   修复前的失败结论 —— 图已经修好了、界面却说它没过，
                #   那是最糟的一种不一致（人看到的是旧结论，文件是新内容）。
                _log(fh, "validate", slot_id=slot["id"], passed=verdict["passed"],
                     failed=verdict["failed"], autofixed=True,
                     checks=[{"name": c["name"], "ok": c["ok"]}
                             for c in verdict["checks"]])

            results.append({
                "slot_id": slot["id"], "role": slot.get("role"),
                "purpose": slot.get("purpose"), "renderer": slot["renderer"],
                "ok": True, "path": art.get("path"),
                "placeholder": bool(art.get("placeholder")),
                "elapsed_s": elapsed_s,
                "validation": {"passed": verdict["passed"],
                               "failed": verdict["failed"]},
                "autofix": fix_info,
                "detail": detail,
            })

        # 只补记**还没记过**的（即入口就缺料的那批）。运行时跳过在发生的那一刻已经记过，
        # 收尾再记一遍会让「这个坑位被跳过了几次」这类统计直接翻倍 ——
        # 日志里重复的事件比缺事件更难查。
        for k in p.skipped:
            if k.get("logged"):
                continue
            _log(fh, "slot_skipped", slot_id=k["slot_id"], missing=k["missing"],
                 cause=k.get("cause"), reason=k["reason"])
        # 实际花掉的模型调用次数 = 声明调模型 **且真调了** 的那些。
        #   两种"没真调"都要扣掉：占位图（无 key，压根没发请求）、复用生成底（重做那一档）。
        #   报"实际"而不是"声明"：审核台的成本条要能回答"这一批花了多少"，
        #   而 p.model_calls 回答的是"如果都跑成，会花多少"—— 两回事。
        used = sum(1 for r in results
                   if r.get("ok") and registry.calls_model(r["renderer"])
                   and not r.get("placeholder")
                   and not (r.get("detail") or {}).get("reused_bg"))
        _log(fh, "run_end", ok=sum(1 for r in results if r.get("ok")),
             total=len(results), skipped=len(p.skipped),
             model_calls_declared=p.model_calls, model_calls_used=used)

    return {"ok": True, "run_dir": str(p.run_dir), "results": results, "plan": p,
            # 实际用的抠图方式（不是"请求的那个"）
            #   请求方式在跑之前就打印过了，但"这台机器上真正走了哪条路"只有
            #   跑完才知道。降级必须**在控制台上看得见** —— 否则"整批主体其实
            #   出自 floodfill"这件事只躺在 run.jsonl 里，等着某个发现边缘毛糙的
            #   人自己去翻。"日志里记了"和"人看见了"不是一回事。
            "subject": ctx.get("subject"),
            "cutouts": ctx.get("cutouts") or {},
            # 实际花掉的调用次数（见上面 run_end 的算法）。run.py 与审核台都读它。
            "model_calls_used": used}


# ---------------------------------------------------------------- redo

# 重做粒度。语义是"**哪一层**要变"，它决定能复用多少既有产物。
#
# 四种粒度与架构三层是一一对应的，不是随手分的档：
#
#     text      文字层（确定性）     拿上一轮的文字底重新叠字
#     placement 合成层（确定性）     只动主体落点/缩放；**背景像素与文字内容都不变**
#     bg        背景层（生成性）     重新生成空背景 —— 全链路唯一会花钱的一档
#     cutout    主体（本 run 唯一一份）  本地重抠，**所有读主体的坑位**一起重出
#
# 前两档免费、后两档一免费一花钱，这个划分本身就是给运营的**代价提示**：
# 七成情况（文案、构图）不花钱，只有背景花钱 —— 而背景恰好是唯一本来就该由
# 模型产生的东西。见 docs/使用形态.md §3.1。
LAYERS = ("text", "placement", "bg", "cutout")

LAYER_DOC = {
    "text": "只重排文字层：拿上一轮留下的文字底重新叠字。不抠图、不合成、不调模型",
    "placement": "位置/大小变了：重跑该格，复用上一轮的 subject.png、素材抠图与生成底",
    "bg": "背景像素变了：重新生成空背景（位置 4 唯一花钱的一档）",
    "cutout": "抠得不干净：本地重抠主体**与素材**，所有用到它们的坑位一起重出一版",
}

# 抠图类产物影响的坑位，判据来自**表里的 needs**与渲染器声明的 cuts，
# 不是坑位号 —— 否则"加一个坑位 = 加一行数据"在这里就断了。
SUBJECT_NEED = "front"


def read_records(run_dir: str | Path, *, tolerant: bool = False,
                 bad_out: list[str] | None = None) -> list[dict]:
    """读 run.jsonl。重做/审核台都从这里读状态 —— **不许有第二个状态源**。

    tolerant=True 用来读**正在被写**的日志（审核台每 700ms 轮询一次，而
    执行线程同时在 append）。写侧是"一次 write 一整行 + flush"，但读到半行
    仍然是可能的 —— 那种情况下 json.loads 会炸，而"看着看着日志突然报错"
    是最不该出现在审核台上的行为。

    ★ 容错**不等于**静默：跳过的行由 bad_out 带出去（消费方 run_state），
      审核台会把它显示成"日志有 N 行读不出来"。日志是唯一的事实来源，
      它自己坏了几行这件事必须浮在上面，而不是被 except 吃掉。
    """
    p = Path(run_dir) / "run.jsonl"
    if not p.exists():
        return []
    out: list[dict] = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            if not tolerant:
                raise
            if bad_out is not None:
                bad_out.append(ln[:200])
    return out


def latest_run(out_dir: str | Path, upc: str) -> Path | None:
    """找这个 UPC 最近一次**可重做**的 run（有 plan.json）。

    为什么按目录名排序而不是按 mtime：目录名里的时间戳是微秒级、单调递增的，
    而 mtime 会因为复制/同步/杀软扫描而变 —— 用 mtime 选"上一轮"会选错。

    消费方有两个：run.py 的 --redo（决定重放哪一轮）与审核台（决定默认展示哪一轮）。
    它必须只有一处实现 —— "上一轮是哪一轮"若有第二个答案，重做就会落到别的目录上。
    """
    out_dir = Path(out_dir)
    cands = [d for d in out_dir.glob(f"{upc}_*")
             if d.is_dir() and (d / "plan.json").exists()]
    return sorted(cands, key=lambda d: d.name)[-1] if cands else None


def next_seq(run_dir: Path, slot: dict, upc: str) -> int:
    """该格在本 run 目录里已有几个版本 —— 重做**新增版本，不覆盖**。

    覆盖会抹掉归因数据：改了文案之后"上一版长什么样"就再也拿不回来了，
    而"哪一版更好"恰恰是运营要靠对比回答的问题。
    """
    prefix = f"{upc}_{slot['id']:02d}_"
    return sum(1 for _ in Path(run_dir).glob(prefix + "*.jpg")) + 1


def _subject_ctx(prev_run_dir: Path) -> dict | None:
    """上一轮留下的主体。重做一格不该重抠整批的主体（不变量 A 的延伸 ——
    主体在一轮 run 里只有一份，重做也沿用那一份，否则轮廓会和其余六张不一样）。
    """
    p = Path(prev_run_dir) / subject_mod.SUBJECT_NAME
    if not p.exists():
        return None
    return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "source": str(p), "reused_from": Path(prev_run_dir).name}


def _load_cutouts(prev_run_dir: Path, kinds: list[str]) -> dict[str, dict]:
    """从 run.jsonl 读回上一轮抠好的素材（**不重新抠**）。

    为什么不重新抠：抠图的 alpha 会随"这次走了哪条路"而变（rembg 与 floodfill
    抠出的紧致 alpha 相差十几万像素）。`--redo 7 --layer placement` 的语义是
    "只挪了一下位置"，如果它顺手重抠了竞品，产出的差异就不止来自被改的那一处 ——
    版本对比立刻失效。所以：**抠一次、复用到这一轮结束**（layer=cutout 除外，
    那一档要的就是重抠）。

    读 run.jsonl 而不是另存一份元数据：重做与审核台共用同一个状态源，
    不许有第二个（见 read_records）。
    """
    out: dict[str, dict] = {}
    recs = [r for r in read_records(prev_run_dir) if r.get("stage") == "cutout"]
    for kind in kinds:
        rec = next((r for r in reversed(recs) if r.get("kind") == kind), None)
        if rec is None:
            raise ValueError(
                f"上一轮没有为 {kind} 留下抠好的素材（run.jsonl 里没有 cutout 记录）—— "
                f"这一轮的重做没有可复用的底。用 layer=cutout 重出一次，或整批重跑。")
        p = Path(str(rec.get("path") or ""))
        if not p.exists():
            raise ValueError(
                f"上一轮记着 {kind} 抠图产物在 {p}，但文件不在了 —— "
                f"用 layer=cutout 重出一份，或整批重跑。")
        out[kind] = {"kind": kind, "path": str(p),
                     "sha256": rec.get("sha256"),
                     "size": rec.get("size"), "source": rec.get("source"),
                     "cutout": {"mode": rec.get("mode")},
                     "alpha_coverage": rec.get("alpha_coverage"),
                     "reused_from": prev_run_dir.name}
    return out


def redo(prev_run_dir: str | Path, product: dict, slot_id: int, *,
         layer: str = "text", base_dir: str | Path | None = None,
         cutout: str | None = None, model: str | None = None,
         progress=None) -> dict:
    """重放某一格（或某一组），新增版本。

    为什么是"重放"而不是"重新跑"：`plan.json` 是整条链路唯一的状态，
    其余产物都是它的确定性映射 —— 所以重做就是重放其中一条。
    重做读的是**当次输入**（`product`）加上**上一轮的产物**（subject.png / raw/）。

    ★ 返回契约是**一组新版本**，不是一格
    ------------------------------------
        text / placement / bg 三种粒度恰好只影响一格，所以 results 长度为 1；
        cutout 影响"所有读主体的坑位"，长度就是那几个。

        为什么不给 cutout 单独开一个函数、让单格重做保持原来的扁平返回：
        调用方（CLI、审核台、验收脚本）会因此需要认两套形状，而"重做总是产出
        一组新版本"本来就是一个统一的事实 —— 单格只是这一组恰有一个。
        让契约跟着事实走，而不是跟着"目前只有一个实现"走。

    一条顺序上的规矩
    ---------------
        **做不做得了，在写任何日志之前就判完**。先写一条 `redo_start` 再抛错，
        run.jsonl 里就留下"已经开始、却什么都没发生"的记录 —— 事后读日志的人
        没法区分"被拒绝的重做"与"跑到一半崩掉的重做"。

    每个版本号在**动手之前一次性算好**：`next_seq` 靠数文件得出，
    边渲染边算会让两个受影响坑位读到同一个数（同一目录、同一 UPC 前缀），
    表现为后一个覆盖前一个 —— 而覆盖正是这一整套设计要防的事。
    """
    prev_run_dir = Path(prev_run_dir)
    if not (prev_run_dir / "plan.json").exists():
        raise ValueError(f"{prev_run_dir} 里没有 plan.json —— 它不是一次可重做的 run")
    if layer not in LAYERS:
        raise ValueError(f"layer={layer!r} 非法，可选：{'/'.join(LAYERS)}")

    cfg = schema.assert_valid()
    brand = load_brand()
    catalog = yaml.safe_load(
        (ROOT / cfg["catalog"]).read_text(encoding="utf-8")) or {}
    export = cfg["export"]
    palette = catalog.get("palette") or {}

    by_id = {s["id"]: s for s in cfg["slots"]}
    slot = by_id.get(slot_id)
    if slot is None:
        raise ValueError(f"坑位表里没有 id={slot_id} 的坑位")

    upc = product.get("upc") or "NOUPC"
    base = Path(base_dir) if base_dir else Path(".")
    supplied, _broken = assets_mod.big_picture_facts(product, base)
    facts = extract_facts(product, brand)

    # 这一轮做过哪些坑位 —— 读 run.jsonl，**不重新按素材算**：
    # 输入过后可能改过，而"这次 run 里有哪些格子"是既成事实。
    # cutout 要靠它决定重出哪几张；其余粒度要靠它拦住"重做一个本来就被跳过的坑位"。
    doable = next((r.get("doable") for r in read_records(prev_run_dir)
                   if r["stage"] == "run_start"), None) or []

    # ---- 1. 先判"做不做得了"（此处之后才允许写日志）
    #
    # cutout 这一档影响的是"所有**用到抠图产物**的坑位"，而"用到"的判据是
    # 表里的 needs（主体的 front）与渲染器声明的 cuts（内容物 / 竞品）——
    # 不是坑位号。于是加一个"也要抠素材"的坑位，只是它那个文件多声明一句。
    def _cut_kinds_of(slots_: list[dict]) -> list[str]:
        seq = [k for s in slots_ for k in registry.cuts_of(s["renderer"])
               if k in supplied]
        return list(dict.fromkeys(seq))          # 去重、保序

    if layer == "cutout":
        if not (supplied.get(SUBJECT_NEED)):
            raise ValueError(
                f"product 里没有 {SUBJECT_NEED} 原片 —— 没有可重抠的主体")
        reads = {SUBJECT_NEED, *_cut_kinds_of([by_id[i] for i in doable
                                               if i in by_id])}
        targets = [by_id[i] for i in doable
                   if i in by_id and reads & set(by_id[i].get("needs") or [])]
        if not targets:
            raise ValueError(
                f"这一轮没有任何坑位用到抠图产物（doable={doable}）—— "
                f"重抠无从生效")
        # 重抠就是把这份产物换掉 —— 所有用到它们的坑位都按新的一份重出
        cut_kinds = _cut_kinds_of(targets)
    else:
        if slot_id not in doable:
            raise ValueError(
                f"位置 {slot_id} 不在这轮做出来的坑位里（doable={doable}）—— "
                f"它上一轮被跳过了，没有可重放的产物")
        targets = [slot]
        # 只取**这一格**要用的素材抠图产物：只重排位置 2 的文案，没理由去碰
        # 内容物/竞品的抠图产物（那会白白多一处可能失败/变化的环节）。
        cut_kinds = _cut_kinds_of([slot])
        if layer == "text" and (slot.get("text") or "none") == "none":
            raise ValueError(
                f"位置 {slot_id} 的 text=none —— 它不出文字，没有文字层可重排。"
                f"用 layer=placement 重跑整格。")
        if layer == "text" and not (prev_run_dir / "raw"
                                    / f"slot{slot_id:02d}_bg.jpg").exists():
            raise ValueError(
                f"上一轮没有为位置 {slot_id} 留下文字底"
                f"（raw/slot{slot_id:02d}_bg.jpg）—— 无法只重排文字。"
                f"用 layer=placement 重跑整格。")

    # ---- 2. 抠图产物：cutout 重抠，其余复用上一轮的
    subject, subj_changed, subj_s = _subject_ctx(prev_run_dir), False, 0.0
    cutouts: dict[str, dict] = {}
    if layer == "cutout":
        before = (subject or {}).get("sha256")
        if progress:
            progress("重抠主体  本地抠图一次（不联网、零 API 成本）…")
        t_sub = time.time()
        try:
            info = subject_mod.prepare(supplied[SUBJECT_NEED], prev_run_dir,
                                       cutout_mode=cutout)
        except subject_mod.SubjectError as exc:
            # 重抠失败 → 什么都没写成（日志在下一步才打开，见上面那条顺序规矩）。
            # 归到 ValueError 这一类：调用方要处理的是"这次重做不可用 + 为什么"，
            # 而不是一个需要看栈的异常。
            raise ValueError(str(exc)) from exc
        subj_s = round(time.time() - t_sub, 3)
        subject = {"path": info["path"], "sha256": info["sha256"],
                   "source": info["source"], "cutout": info.get("cutout"),
                   "alpha_coverage": info.get("alpha_coverage"),
                   "recomputed": True}
        subj_changed = info["sha256"] != before
        # 素材重抠：与主体同一个时刻做完（此刻还没写日志、也没花钱）
        if cut_kinds:
            cutouts, _bad = produce_cutouts(cut_kinds, supplied, prev_run_dir,
                                            cutout_mode=cutout, progress=progress)
            for v in cutouts.values():
                v["recomputed"] = True
            if _bad:
                raise ValueError(
                    "重抠素材失败：" + "；".join(f"{k}：{v}" for k, v in _bad.items())
                    + "。上一轮的产物**没有被改动**（日志也还没写）。")
    else:
        cutouts = _load_cutouts(prev_run_dir, cut_kinds)

    # ---- 3. 版本号一次性算好
    seqs = {s["id"]: next_seq(prev_run_dir, s, upc) for s in targets}
    t0 = time.time()
    if progress:
        ids = "、".join(str(s["id"]) for s in targets)
        progress(f"重做 layer={layer} → 位置 {ids}")

    results: list[dict] = []
    with (prev_run_dir / "run.jsonl").open("a", encoding="utf-8") as fh:
        if layer == "cutout":
            _log(fh, "redo_subject", path=subject["path"],
                 sha256=subject["sha256"],
                 changed=subj_changed, cutout_mode=(subject.get("cutout") or {}).get("mode"),
                 alpha_coverage=subject.get("alpha_coverage"),
                 elapsed_s=subj_s, targets=[s["id"] for s in targets])

        for s in targets:
            seq = seqs[s["id"]]
            sp = _slot_plan(s, facts)
            ts = time.time()          # 逐格计时：cutout 一次要重出好几格，
                                      # 用同一个 t0 会让后面的格子看起来越来越慢
            _log(fh, "redo_start", slot_id=s["id"], layer=layer, seq=seq,
                 renderer=s["renderer"])

            if layer == "text":
                # ★ 这一条路**完全不碰像素合成**：背景底原样复用，只重新叠字。
                bg_under_text = prev_run_dir / "raw" / f"slot{s['id']:02d}_bg.jpg"
                art = textlayer.overlay_callouts(bg_under_text, prev_run_dir, sp, s,
                                                 brand, export, upc, seq=seq,
                                                 palette=palette)
                art.update({"renderer": f"{s['renderer']}(text-only)",
                            "placeholder": False,
                            "reused_bg": str(bg_under_text),
                            "subject_sha256": (subject or {}).get("sha256")})
            else:
                # 生成底什么时候能复用：**背景像素本来就不该变**的那些粒度。
                #   placement / cutout —— 只动了主体，背景是上一轮已经生成好的同一张；
                #   bg               —— 这一档要的就是换背景，当然重新生成。
                # 这一条把「位置或大小不对 = 免费」从文案变成了事实：
                # 否则位置 4 调一次模型只为了让主体挪 20 像素，那是白花的钱。
                reuse = None
                if layer in ("placement", "cutout") and \
                        registry.calls_model(s["renderer"]):
                    cand = prev_run_dir / "raw" / f"slot{s['id']:02d}_gen.jpg"
                    if cand.exists():
                        reuse = str(cand)
                ctx = {
                    "upc": upc, "stamp": prev_run_dir.name,
                    "run_dir": str(prev_run_dir), "out_dir": str(prev_run_dir.parent),
                    "export": export, "catalog": catalog, "brand": brand,
                    "facts": facts, "supplied": supplied, "seq": seq,
                    "subject": subject, "model": model, "reuse_bg": reuse,
                    "cutout_mode": cutout,
                    # 素材抠图产物：非 cutout 档复用上一轮的（**不重抠**，
                    # 否则"只改了位置"这句话就不成立，见 _load_cutouts）
                    "cutouts": cutouts,
                }
                # 唯二分派点仍然是同一行 —— 重做不是第二条链路，它只是"跑一条"。
                art = registry.get(s["renderer"])(s, {**ctx, "plan": sp})

            elapsed = round(time.time() - ts, 3)
            detail = _jsonable({k: v for k, v in art.items() if k != "path"})
            _log(fh, "redo", slot_id=s["id"], layer=layer, seq=seq,
                 renderer=s["renderer"], path=art.get("path"),
                 elapsed_s=elapsed, subject_sha256=(subject or {}).get("sha256"),
                 detail=detail)

            verdict = validators.validate(
                art["path"], {**s, "validate_rules": sp.get("validate_rules")},
                export, upc)
            _log(fh, "validate", slot_id=s["id"], passed=verdict["passed"],
                 failed=verdict["failed"], redo=True, seq=seq,
                 checks=[{"name": c["name"], "ok": c["ok"]} for c in verdict["checks"]])

            results.append({
                "slot_id": s["id"], "seq": seq, "path": art.get("path"),
                "renderer": s["renderer"], "elapsed_s": elapsed,
                "placeholder": bool(art.get("placeholder")),
                "reused_bg": art.get("reused_bg"),
                "callouts": art.get("callouts") or [],
                "validation": {"passed": verdict["passed"],
                               "failed": verdict["failed"]},
            })
            if progress:
                mark = "（占位图）" if art.get("placeholder") else ""
                progress(f"        ✓ 位置 {s['id']} 第 {seq} 版 "
                         f"{Path(str(art.get('path') or '')).name} {mark}")

        # 本次重做实际发生的模型调用：声明调模型、但没复用生成底的那些。
        # 报"实际"而不是"声明" —— 审核台要拿它算这一批花了多少。
        called = sum(1 for r in results
                     if registry.calls_model(r["renderer"]) and not r["reused_bg"])
        # 重做也要留一条**结论**记录，不能只留过程。
        #   为什么：审核台的日志条要回答"这一轮重做过几次、哪一档、花了没有"，
        #   而那需要"这次重做整体怎么样"这一条。缺了它，界面就只能去数
        #   redo 记录的条数再猜 layer —— 那是在界面里重算一遍事实。
        _log(fh, "redo_end", layer=layer, slots=[r["slot_id"] for r in results],
             model_calls=called, elapsed_s=round(time.time() - t0, 3),
             subject_changed=(subj_changed if layer == "cutout" else None))

    return {
        "ok": True, "run_dir": str(prev_run_dir), "layer": layer,
        "layer_doc": LAYER_DOC[layer],
        "subject": ({"sha256": subject["sha256"], "changed": subj_changed,
                     "elapsed_s": subj_s, "cutout_mode":
                     (subject.get("cutout") or {}).get("mode"),
                     "alpha_coverage": subject.get("alpha_coverage")}
                    if subject else None),
        # 这次用到的素材抠图产物（cutout 档是重抠的，其余是复用的）——
        # 调用方要能回答"这一版用的是哪一份竞品抠图"。
        "cutouts": {k: {"path": v["path"], "sha256": v.get("sha256"),
                        "recomputed": bool(v.get("recomputed"))}
                    for k, v in cutouts.items()},
        "results": results,
        "model_calls": called,
        "elapsed_s": round(time.time() - t0, 3),
    }


# ---------------------------------------------------------------- 审核台读模型
#
# 为什么这一层要长在 orchestrator 里，而不是长在 web/server.py 里：
#   "每格现在有几版 / 最新版是哪一版 / 被采纳了没有 / 为什么跳过"这几个问题，
#   答案只写在 plan.json 与 run.jsonl 里。让后端去解析它们，等于把规则
#   （版本号怎么算、采纳怎么判定）搬进接口层；再让前端去解析一次，就有两份了。
#   所以规则留在**拥有那份日志的模块**里，接口层只做转发。


def _seq_from_path(p) -> int | None:
    """从成品文件名尾号取版本号。

    filename_pattern = `{upc}_{slot}_{role}_{seq}`（见 synth.filename_for），
    所以尾号就是 seq。初始那一条 render 记录不带 seq 字段（那时还没有"版本"这件事），
    但它落盘的文件名里已经带着 1 —— 从文件名取，比在日志里补一个字段更不容易漂。
    """
    if not p:
        return None
    tail = Path(str(p)).stem.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _layers_ok(sp: dict, run_dir: Path) -> list[str]:
    """这一格**界面上能点**的重做档位。

    ★ 判据仍以 `redo()` 为准 —— 这里只决定"按钮显不显示"。
      两处都判是刻意的：把判据全部推给后端，界面就会给位置 1 摆出"文案不对"
      （而它的 text=none，点了必然报错）；把判据全部搬进界面，就是又一份规则。
      所以这里算**能不能点**，后端算**做不做得了**。

    text      要求本格出字，且上一轮真的留下了文字底（raw/slotNN_bg.jpg）
    placement 恒可点（它只重跑这一格）
    bg        只对**调模型**的渲染器有意义 —— 零模型的格子没有"背景层"可换
    cutout    只要这一格读抠图产物（主体 front 或素材 cuts）就成立；
              注意它**不止影响这一格**，所有读同一份产物的坑位会一起重出（不变量 A）
    """
    sid = sp["slot_id"]
    out: list[str] = []
    if (sp.get("text") or "none") != "none" and \
            (run_dir / "raw" / f"slot{sid:02d}_bg.jpg").exists():
        out.append("text")
    out.append("placement")
    rname = str(sp.get("renderer"))
    if registry.calls_model(rname):
        out.append("bg")
    if "front" in (sp.get("needs") or []) or registry.cuts_of(rname):
        out.append("cutout")
    return out


def _slot_state(sp: dict, vers: dict[int, dict], acc_seq, acc_by, acc_ok: bool,
                run_dir: Path) -> dict:
    """把一个坑位的"计划 + 版本 + 采纳"压成界面要的形状。"""
    vs = [vers[k] for k in sorted(vers)]
    latest = vs[-1] if vs else None
    accepted_version = vers.get(acc_seq) if (acc_ok and acc_seq is not None) else None
    return {
        "slot_id": sp["slot_id"],
        "role": sp.get("role"),
        "purpose": sp.get("purpose"),
        "renderer": sp.get("renderer"),
        "text": sp.get("text"),
        "background": sp.get("background"),
        "mandatory": bool(sp.get("mandatory")),
        "needs": sp.get("needs") or [],
        "callouts": sp.get("callouts") or [],
        "validate_rules": sp.get("validate_rules") or [],
        # calls_model 取自 registry 的**声明**（不是跑出来的事实）：声明是稳定的，
        # 而"这次到底调没调"由 placeholder 与 reused_bg 决定，属于版本上的事实。
        "calls_model": registry.calls_model(str(sp.get("renderer"))),
        "status": "done" if vs else "pending",
        "missing": [],
        "reason": None,
        "layers": _layers_ok(sp, run_dir),
        "versions": vs,
        "latest": latest,
        # ★ 采纳状态不是另存的一个字段，而是**从日志顺序推出来的**：
        #   最后一条 accept 若晚于最后一条 redo，就是"已采纳"。
        #   这条判据同时覆盖两种真实情形，而它们都需要被正确表达：
        #     · 采纳了 v1，之后又重做出 v2  → v1 那次采纳**作废**，回到待审
        #       （使用形态 §2.4：已采纳 --重做--> 仅当前张回到待审）
        #     · 已经有 v2，人比较后**仍然采纳 v1** → 成立，且交付的必须是 v1
        #   若写成"采纳版号 == 最新版号"，第二种情形永远登记不上；
        #   若写成"有过 accept 就算采纳"，第一种情形就回不到待审。
        "accepted": accepted_version is not None,
        "accepted_seq": acc_seq if accepted_version is not None else None,
        "accepted_by": acc_by if accepted_version is not None else None,
        "accepted_version": accepted_version,
        "redo_count": sum(1 for v in vs if v["layer"] != "initial"),
    }


def run_state(run_dir: str | Path) -> dict:
    """一次 run 的**读模型**：审核台、CI 断言、导出都用这一份。

    它只由两样东西派生，不引入第三个状态源：
        plan.json  —— 当时的**计划**（做哪几张、每张什么形状、签字状态）
        run.jsonl  —— 当时的**经过**（每格出了什么、校验结论、重做与采纳）

    日志里有读不出来的行时，它**不假装没发生**：`log_bad_lines` 报出去，
    审核台会显示出来。日志是唯一的事实来源，它自己坏了几行这件事必须浮在上面。
    """
    run_dir = Path(run_dir)
    plan: dict = {}
    pp = run_dir / "plan.json"
    if pp.exists():
        plan = json.loads(pp.read_text(encoding="utf-8"))

    bad: list[str] = []
    recs = read_records(run_dir, tolerant=True, bad_out=bad)
    start = next((r for r in recs if r.get("stage") == "run_start"), {})
    end = next((r for r in reversed(recs) if r.get("stage") == "run_end"), None)

    # ---- 版本：初始渲染与重做两种记录共同构成"这一格有哪几版"
    vers: dict[int, dict[int, dict]] = {}
    for r in recs:
        if r.get("stage") not in ("render", "redo"):
            continue
        sid = r.get("slot_id")
        seq = int(r.get("seq") or _seq_from_path(r.get("path")) or 1)
        p = str(r.get("path") or "")
        vers.setdefault(sid, {})[seq] = {
            "seq": seq, "path": p, "file": Path(p).name if p else None,
            "exists": bool(p) and Path(p).exists(),
            "elapsed_s": r.get("elapsed_s"),
            "placeholder": bool(r.get("placeholder")),
            "layer": "initial" if r.get("stage") == "render" else r.get("layer"),
            "ts": r.get("ts"),
            "subject_sha256": r.get("subject_sha256"),
            "validation": None,
        }
    # 校验结论按 (坑位, 版本号) 贴回去 —— 初始那一条 validate 不带 seq，
    # 而初始渲染的版本号恒为 1，所以它能对上（不属于"猜"，属于定义）。
    for r in recs:
        if r.get("stage") != "validate":
            continue
        v = vers.get(r.get("slot_id"), {}).get(int(r.get("seq") or 1))
        if v is not None:
            v["validation"] = {"passed": r.get("passed"),
                               "failed": r.get("failed") or []}

    # ---- 采纳：只记"最后一条 accept 出现在第几行"与"最后一条 redo 在第几行"。
    #      "已采纳"= 最后那次采纳晚于最后那次重做（见 _slot_state 的说明）。
    #      记行号而不是记时间戳：日志是追加写的，行号就是顺序，没有第二个时钟。
    last_acc: dict[int, int] = {}
    last_redo: dict[int, int] = {}
    acc_seq: dict[int, int] = {}
    acc_by: dict[int, str] = {}
    for i, r in enumerate(recs):
        st = r.get("stage")
        if st == "accept":
            last_acc[r.get("slot_id")] = i
            acc_seq[r.get("slot_id")] = r.get("seq")
            acc_by[r.get("slot_id")] = r.get("by")
        elif st == "redo":
            last_redo[r.get("slot_id")] = i

    skipped = {k.get("slot_id"): k for k in
               (plan.get("skipped") or start.get("skipped") or [])}

    # ---- 组装：先按计划的顺序排（plan.json 里就是表里的顺序），再补跳过的那几格
    slots: list[dict] = []
    for sp in plan.get("slots") or []:
        sid = sp["slot_id"]
        acc_ok = (last_acc.get(sid) is not None
                  and last_acc[sid] > last_redo.get(sid, -1))
        slots.append(_slot_state(sp, vers.get(sid, {}), acc_seq.get(sid),
                                 acc_by.get(sid), acc_ok, run_dir))
    have = {s["slot_id"] for s in slots}
    for sid, k in skipped.items():
        if sid in have:
            continue
        slots.append({
            "slot_id": sid, "role": k.get("role"), "purpose": k.get("purpose"),
            "renderer": k.get("renderer"), "text": None, "background": None,
            "mandatory": False, "needs": k.get("missing") or [],
            "callouts": [], "validate_rules": [],
            "calls_model": registry.calls_model(str(k.get("renderer"))),
            "status": "skipped", "missing": k.get("missing") or [],
            "reason": k.get("reason"), "layers": [], "versions": [], "latest": None,
            "accepted": False, "accepted_seq": None, "accepted_by": None,
            "accepted_version": None, "redo_count": 0,
        })
    slots.sort(key=lambda s: s["slot_id"])

    done = [s for s in slots if s["status"] == "done"]
    redo_ends = [r for r in recs if r.get("stage") == "redo_end"]

    # ---- 主体与素材抠图的**实际**方式（不是请求的那个）
    srec = next((r for r in reversed(recs)
                 if r.get("stage") in ("subject", "redo_subject")), None)
    subject = None
    if srec:
        subject = {
            "path": srec.get("path"), "sha256": srec.get("sha256"),
            # 两处记录给同一个事实起了不同的键（subject 用 mode / redo_subject
            # 用 cutout_mode）—— 在这里归一，界面就只看一个名字。
            "mode": srec.get("mode") or srec.get("cutout_mode"),
            "alpha_coverage": srec.get("alpha_coverage"),
            "recomputed": srec.get("stage") == "redo_subject",
        }
    cutouts: dict[str, dict] = {}
    for r in recs:
        if r.get("stage") == "cutout":
            cutouts[r.get("kind")] = {
                "path": r.get("path"), "sha256": r.get("sha256"),
                "mode": r.get("mode"), "alpha_coverage": r.get("alpha_coverage"),
            }

    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "upc": plan.get("upc") or start.get("upc"),
        "stamp": plan.get("stamp") or start.get("stamp"),
        "product": plan.get("product") or start.get("product"),
        "facts": plan.get("facts") or {},
        "supplied": plan.get("supplied") or {},
        "broken": plan.get("broken") or {},
        "e0": plan.get("e0"),
        "attest_missing": plan.get("attest_missing") or [],
        "subject": subject,
        "cutouts": cutouts,
        "slots": slots,
        "counts": {
            "table": len(slots),
            "done": len(done),
            "pending": sum(1 for s in slots if s["status"] == "pending"),
            "skipped": sum(1 for s in slots if s["status"] == "skipped"),
            "accepted": sum(1 for s in done if s["accepted"]),
            "redo": sum(s["redo_count"] for s in slots),
            # 三个数字**分开报**，因为它们是三笔不同的账：
            # 计划里本要花几次、这一轮实际花了几次、重做又花了几次。
            # 前两个对 M7 之前的 run 没有（那时还没记），回落到 run_start 里的
            # 计划值；再没有就是 None —— 界面显示"—"，不拿别的数顶替。
            "model_calls_declared": (plan.get("model_calls")
                                     if plan.get("model_calls") is not None
                                     else start.get("model_calls")),
            "model_calls_used": (end or {}).get("model_calls_used"),
            "model_calls_redo": sum(r.get("model_calls") or 0 for r in redo_ends),
            "placeholder": sum(1 for s in done if (s["latest"] or {}).get("placeholder")),
        },
        "finished": end is not None,
        "log_bad_lines": len(bad),
        "log_lines": len(recs),
    }


def mark_accept(run_dir: str | Path, slot_id: int, *, seq: int | None = None,
                by: str | None = None) -> dict:
    """把"这一版被采纳"写进 run.jsonl，返回新的 run_state。

    为什么采纳也要落盘：采纳率是外环回流的原料（使用形态 §3.2）——
    "哪个坑位、哪一版被采纳"只有写下来才存在。而它写进 **run.jsonl 而不是
    另开一个审核状态文件**：状态源只许有一个（见 read_records）。

    ★ 只记"采纳了第几版"，**不记"取消采纳"**。因为取消这件事不需要记：
      它由**日志顺序**推出 —— 最后一条 accept 若早于最后一条 redo，那次采纳就作废。
      于是重做之后自动回到待审，没人需要记得去清状态（见 _slot_state.accepted）。
    """
    run_dir = Path(run_dir)
    if not (run_dir / "plan.json").exists():
        raise ValueError(f"{run_dir} 里没有 plan.json —— 它不是一次可审的 run")
    st = run_state(run_dir)
    slot = next((s for s in st["slots"] if s["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError(f"这次 run 里没有位置 {slot_id}")
    if not slot["versions"]:
        raise ValueError(
            f"位置 {slot_id} 这一轮没有产出任何版本（{slot['status']}），无从采纳")
    seqs = [v["seq"] for v in slot["versions"]]
    if seq is None:
        seq = seqs[-1]
    if seq not in seqs:
        raise ValueError(f"位置 {slot_id} 没有第 {seq} 版（现有版本：{seqs}）")
    with (run_dir / "run.jsonl").open("a", encoding="utf-8") as fh:
        _log(fh, "accept", slot_id=slot_id, seq=seq, by=by)
    return run_state(run_dir)


# ---------------------------------------------------------------- 交付

EXPORT_DIRNAME = "export"
EXPORT_MANIFEST = "交付清单.json"


def export_bundle(run_dir: str | Path) -> dict:
    """把这一轮**被采纳的那几版**固化成一份交付清单（写到 `export/` 里）。

    为什么需要它：run 目录里躺着的是"这一格有哪几版"（`_1` `_2` `_3`），
    而交付要回答的是"**这一批交出去的是哪几版**"。后者不写下来就不存在 ——
    运营把文件拖进亚马逊后台时，没有任何东西告诉他 `_2` 才是采纳的那一版。
    清单里带 sha256：交付物事后被替换过，是能验出来的。

    ★ 导出的必须是**被采纳的那一版**，不是"目录里最新的那一版"。
      两者常常是同一版（最近一次采纳的通常就是最新版），但"人是比较之后才选"的
      恰恰是它们**不同**的那些场合 —— 导出最新版等于把人的判断丢掉。

    为什么要求"全部已采纳"才允许导出：这是设计里写定的流转
    （使用形态 §2.4「七张全部已采纳 ⇒ 可导出」）。半批导出会产出
    "一部分是人选的、一部分是默认的"这种没人能负责的东西。

    导出**不做上传**：上传需要账号权限与平台审核反馈，工具不碰（使用形态 §7）。
    导出的终点是本地目录，这是刻意的。
    """
    run_dir = Path(run_dir)
    st = run_state(run_dir)
    done = [s for s in st["slots"] if s["status"] == "done"]
    if not done:
        raise ValueError("这一轮没有任何产出，无可交付")
    not_yet = [s["slot_id"] for s in done if not s["accepted"]]
    if not_yet:
        raise ValueError(
            "位置 " + "、".join(str(i) for i in not_yet) + " 还没有采纳 —— "
            "交付的是\u201c被采纳的那几版\u201d，不是\u201c目录里最新的那几版\u201d")

    files = []
    for s in done:
        v = s["accepted_version"]
        p = Path(str(v["path"]))
        files.append({
            "slot_id": s["slot_id"], "role": s["role"], "purpose": s["purpose"],
            "seq": v["seq"], "file": v["file"], "path": str(p),
            "size_bytes": p.stat().st_size if p.exists() else None,
            "sha256": (hashlib.sha256(p.read_bytes()).hexdigest()
                       if p.exists() else None),
            "validation_passed": ((v.get("validation") or {}).get("passed")),
        })

    out = run_dir / EXPORT_DIRNAME
    out.mkdir(exist_ok=True)
    manifest = {
        "upc": st["upc"], "run_id": st["run_id"], "run_dir": str(run_dir),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "files": files,
        "skipped": [{"slot_id": s["slot_id"], "purpose": s["purpose"],
                     "missing": s["missing"], "reason": s["reason"]}
                    for s in st["slots"] if s["status"] == "skipped"],
        "model_calls": {
            "declared": st["counts"]["model_calls_declared"],
            "used": st["counts"]["model_calls_used"],
            "redo": st["counts"]["model_calls_redo"],
        },
        "note": ("只列**被采纳**的版本；同一坑位的其它版本仍在 run 目录里，"
                 "供事后对比。skipped 是这次没做的坑位与原因 —— "
                 "它们不是失败，是缺料跳过。"),
    }
    (out / EXPORT_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "manifest": str(out / EXPORT_MANIFEST),
            "manifest_dir": str(out), "files": files,
            "skipped": manifest["skipped"], "counts": st["counts"]}
