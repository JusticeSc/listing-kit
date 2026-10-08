# -*- coding: utf-8 -*-
"""离线只读数据源：把商品包与已冻结的产物装配成一次可走查的会话（Phase 2 / D2.R1）。

这一层只做三件事：

1. 按**商品包**解析出这次演示用的每一个权威对象（参考包、事实、计划、提示词、候选）；
2. 把后半链（PC-08 – PC-12）的判定跑在**已经冻结的真实产物**上 —— 事实验证不跑模型，
   审美与事实签字读的是人工记录；
3. 把用户可以做的动作（确认方案、编辑提示词、选返工原因、选择候选）落在**内存**里。

它不写任何文件、不连任何网络，而且这不是"暂时"：`app/server.py --check` 把这两条
当判据跑 —— 运行前后项目目录的文件指纹必须逐字节一致，任何 socket 连接尝试都会让它失败。

边界（要说清楚，否则界面会替后端吹牛）：

* 候选 manifest 里存的是绝对路径，这批产物换目录即失效（state 已登记
  `run_manifest_stores_absolute_paths_not_portable`）。离线模式按 manifest 读回，
  不承诺"搬到别处也能跑"。
* 本期只有场景图那一张有真实候选；其余几张的候选要等 Phase 4 的真实生成。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.core import back_chain as BC          # noqa: E402
from demo.core import contracts as C            # noqa: E402
from demo.core import front_chain as FC         # noqa: E402
from demo.core import packages as PKG           # noqa: E402

FAKE_ACTIONS = (
    ("生成候选", "正式版会调用阿里云百炼的图生图，把商品参考图真的发过去",
     "离线演示，不调用模型"),
    ("重做这一张", "正式版会为这一张图开一次新的生成尝试，旧候选原样保留",
     "离线演示，不产生新候选"),
    ("导出", "正式版会把选中的成品、清单和说明写成一个可核验的目录",
     "离线演示，不写文件"),
)

# 返工的归类名只用于显示；归类本身由 back_chain.REASON_CODES 决定，不在这里另立一套。
CATEGORY_LABEL = {
    "technical_form": "技术形态",
    "scene_composition": "场景与构图",
    "identity": "身份与结构",
    "exact_text": "精确文字",
    "unclassified": "归不了类",
}


class OfflineError(RuntimeError):
    """离线装配失败：缺料或数据不成形。缺料要报缺料，不拿别的商品顶上。"""


@dataclass
class Session:
    """一次走查会话。全部状态在内存里；进程重启即回到冻结点。"""

    project: Path
    sku: str
    package: dict = field(default_factory=dict)
    card: dict = field(default_factory=dict)
    steps: dict = field(default_factory=dict)
    plan_confirmed: bool = False
    prompts: dict = field(default_factory=dict)
    prompt_history: dict = field(default_factory=dict)
    candidates: dict = field(default_factory=dict)
    candidate_shot: str = ""
    technical: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)
    reviews: dict = field(default_factory=dict)
    rules: dict = field(default_factory=dict)
    selection: dict | None = None
    rework: dict | None = None
    flash: str = ""          # 一次性提示语，只给界面用；它不是业务状态
    notes: list = field(default_factory=list)

    def pop_flash(self) -> str:
        value, self.flash = self.flash, ""
        return value

    # ------------------------------------------------------------------ 读
    @property
    def plan(self) -> dict:
        res = self.steps.get("PC-03")
        return (res.payload if res else {}) or {}

    def shots(self) -> list:
        return list(self.plan.get("shots") or [])

    def prompt(self, shot_id: str):
        return self.prompts.get(shot_id)

    def candidates_of_shot(self, shot_id: str) -> list:
        if shot_id != self.candidate_shot:
            return []
        return sorted(self.candidates)

    def blockers(self) -> list:
        """真正挡住流程的环节。PC-03 未确认是**预期状态**，不算挡住。"""
        out = []
        for cid in ("PC-01", "PC-02", "PC-04"):
            res = self.steps.get(cid)
            if res is None or not res.accepted:
                out.append((cid, res))
        p3 = self.steps.get("PC-03")
        if p3 is None or p3.outcome not in ("accepted", "business_reject"):
            out.append(("PC-03", p3))
        return out

    # ------------------------------------------------------------------ 写（只在内存）
    def confirm_plan(self, confirmed_by: str = "演示用户"):
        if "PC-01" not in self.steps or "PC-02" not in self.steps:
            # 装配没走通时不给方案：按合同回一个 business_reject，而不是抛异常。
            # （入口层已经不让这种会话走到这一步；这里是第二道，防止点出一条堆栈。）
            return C.StepResult("PC-03", "business_reject",
                                notes=["这一步要先有素材与事实检查的结果；现在是缺的，"
                                       "所以不给方案，也不猜它通过"])
        res = FC.propose_plan(self.steps["PC-02"].payload, self.steps["PC-01"].payload,
                              FC.platform_rules(self.project), confirmed_by=confirmed_by)
        self.steps["PC-03"] = res
        self.plan_confirmed = res.accepted
        return res

    def edit_prompt(self, shot_id: str, *, append=None, raw_text=None):
        cur = self.prompts.get(shot_id)
        if cur is None:
            return None
        res = FC.edit_prompt(cur, append=append, raw_text=raw_text)
        if res.accepted:
            self.prompts[shot_id] = res.payload
            self.prompt_history.setdefault(shot_id, []).append(res.payload)
        return res

    def run_rework(self, shot_id: str, reason_code: str):
        res = BC.rework(shot_id=shot_id, reason_code=reason_code, plan=self.plan,
                        prompt_version=self.prompts.get(shot_id), state=self.rework_state())
        self.rework = res.as_dict()
        return res

    def select(self, candidate_id: str):
        res = BC.select_candidate(shot_id=self.candidate_shot,
                                  candidate=self.candidates[candidate_id],
                                  fact_result=self.facts[candidate_id],
                                  review=self.steps.get("PC-10"),
                                  existing=self.selection)
        if res.accepted:
            self.selection = res.payload["selection"]
        return res

    def rework_state(self) -> dict:
        """给返工路由看"哪些图不该被碰"：逐图的候选身份与提交次数。"""
        shots = {}
        for shot in self.shots():
            sid = shot["shot_id"]
            cids = self.candidates_of_shot(sid)
            shots[sid] = {"candidate_sha256": [self.candidates[c]["sha256"] for c in cids],
                          "submit_count": len(cids)}
        return {"shots": shots}


def build(project=ROOT, sku=None) -> Session:
    """按商品包装配一次会话。缺料一律转成 OfflineError：报得出来，不抛堆栈。

    为什么在**这一层**统一转：装配要读五份结构性文件（事实卡、提示词 profile、
    验证路由计划、参考包声明、候选来源声明），它们由链上不同环节按需读。以前哪一环先
    读、哪一环就抛 `PackageError`，入口层只接了 `OfflineError`，于是"缺一份文件"这件事
    在命令行上表现为一段 Python 堆栈（2026-09-26 实测：verifier_plan / prompt_profile /
    reference_pack 三份都这样）。缺料是业务事件，不是程序异常 —— 在这里一次转干净。
    """
    try:
        return _assemble(project, sku)
    except PKG.PackageError as exc:
        raise OfflineError(str(exc)) from None


def _assemble(project=ROOT, sku=None) -> Session:
    """装配本体。缺料如实报缺料，不静默换商品。"""
    project = Path(project).resolve()
    try:
        pkg = PKG.resolve(project, sku)
    except PKG.PackageError as exc:
        raise OfflineError(str(exc)) from None

    # 八页要用到包里的每一份文件：少任何一份，后面总有一页是空的。
    # COMPLETE_KEYS 是"这条链跑起来的结构性前提"；这里更严一点，用的是**同一张登记表**
    # （PKG.FILES），不另立第二套齐套标准。缺一份就停在这里，说清缺哪一份，
    # 而不是让某一页悄悄空着。（第二商品 bex-02 只有两份文件，它不是这个入口的完整包。）
    present = pkg.presence()
    missing = [name for key, name in PKG.FILES.items() if not present.get(key)]
    if missing:
        raise OfflineError("商品包 " + pkg.sku + " 缺 " + "、".join(missing)
                           + "（在 " + pkg.root.relative_to(project).as_posix()
                           + " 里）—— 缺料要报缺料：补回来再跑，不拿别的数据顶上来")

    s = Session(project=project, sku=pkg.sku, package=pkg.as_ref(), card=pkg.load("card"))
    s.steps["PC-01"] = ref = FC.intake(project, pkg.sku)
    if not ref.accepted:
        return s
    s.steps["PC-02"] = fx = FC.facts(project, ref.payload, sku=pkg.sku)
    if not fx.accepted:
        return s
    s.steps["PC-03"] = plan_res = FC.propose_plan(fx.payload, ref.payload,
                                                  FC.platform_rules(project))
    s.steps["PC-04"] = style = FC.style_spec(plan_res.payload.get("plan_version"), fx.payload,
                                             project=project, sku=pkg.sku)
    if not style.accepted:
        return s
    for shot in plan_res.payload.get("shots") or []:
        res = FC.compile_prompt(plan_res.payload, fx.payload, style.payload,
                                shot["shot_id"], project=project, sku=pkg.sku)
        if res.accepted:
            s.prompts[shot["shot_id"]] = res.payload
            s.prompt_history[shot["shot_id"]] = [res.payload]
        else:
            s.notes.append(f"提示词编不出来：{shot['shot_id']}：" + "；".join(res.notes))
    _load_back_half(s, pkg)
    return s


def _load_back_half(s: Session, pkg) -> None:
    """后半链：候选、技术检查、事实验证、审美。全部只读，且不跑模型。"""
    proj, sku = s.project, pkg.sku
    try:
        s.candidates = BC.candidates_of(proj, sku)
    except Exception as exc:                      # noqa: BLE001
        s.notes.append(f"候选来源读不出来：{type(exc).__name__}: {exc}")
        return

    human_visual = pkg.load("human_visual") if pkg.has("human_visual") else {}
    s.candidate_shot = str(human_visual.get("shot_id") or "")
    card = pkg.load("card")
    verifier_plan = pkg.load("verifier_plan")
    human_facts = pkg.load("human_facts") if pkg.has("human_facts") else {}
    rules = BC.export_rules(proj)
    s.rules = dict(rules)

    for cid in sorted(s.candidates):
        cand = s.candidates[cid]
        s.technical[cid] = BC.technical_check(cand, rules)
        s.facts[cid] = BC.fact_routing(cand, card, verifier_plan, human_facts,
                                       run_models=False, project=proj, sku=sku)

    if s.candidate_shot and s.candidates:
        rev = BC.visual_review(s.candidate_shot, sorted(s.candidates), human_visual,
                               project=proj, sku=sku)
        s.steps["PC-10"] = rev
        s.reviews = rev.payload.get("reviews") or {}


def reason_codes() -> list:
    """返工原因的封闭集合与它归到哪一类 —— 权威是 back_chain.REASON_CODES。"""
    return [{"code": code, "category": BC.classify_reason(code),
             "label": CATEGORY_LABEL.get(BC.classify_reason(code), BC.classify_reason(code))}
            for code in sorted(BC.REASON_CODES)]


def reason_route(category: str) -> dict:
    route = BC.REWORK_ROUTES.get(category) or BC.REWORK_ROUTES["unclassified"]
    return {"changes": list(route["changes"]), "touches_prompt": route["touches_prompt"],
            "why": route["why"]}


def copy_records(s: Session) -> list:
    """这一期有没有要叠上去的文案 —— 只从方案（PC-03）读，界面不写死这个结论。

    空列表表示没有文案记录：PC-12 会记恒等合成。有记录就表示成品要经过排版层，
    而排版层不在这条离线走查里 —— 那种情况下界面必须说「未知」，不许按原样算成功。
    """
    step = s.steps.get("PC-03")
    payload = (step.payload if step else None) or {}
    return list(payload.get("claims") or [])


def selectability(s: Session, candidate_id: str) -> dict:
    """一个候选现在能不能被选中，以及不能的原因 —— 界面据此禁用按钮并说明理由。"""
    if s.selection is not None:
        if s.selection["candidate_id"] == candidate_id:
            return {"ok": False, "why": "这一张已经被选中"}
        return {"ok": False,
                "why": "这一张已经有选择了；改选属于另一个动作，不在这里悄悄覆盖"}
    fact = s.facts.get(candidate_id)
    if fact is None or not fact.accepted:
        return {"ok": False, "why": "商品事实还没有全部落定，不能选"}
    rev = s.reviews.get(candidate_id)
    if rev is None:
        return {"ok": False, "why": "还没有人工审美结论，不能自动选中"}
    if rev.get("verdict") != "keep":
        return {"ok": False, "why": f"人工判定是 {rev.get('verdict')}，不能作为最终选择"}
    return {"ok": True, "why": ""}
