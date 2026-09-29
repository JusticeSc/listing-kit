# -*- coding: utf-8 -*-
"""PC-01 – PC-07 前半链实现（离线、零付费调用）。

它存在的目的是让 §4.4 的合同**能够被证伪**：每条合同都要有一个真实能跑的实现，
以及若干注入缺陷的反例。没有实现的合同只是散文。

三条纪律：

1. **状态不许自造。** 所有返回值都经过 `contracts.StepResult`，
   `outcome` 必须落在该合同自己声明的集合里。所以 PC-03 不能返回 `needs_human`
   （它的合同没声明这个结果），PC-04 可以 —— 这不是风格问题，是合同问题。
2. **上游不过，下游不写。** 上游非 accepted 时下游返回 `blocked_by`，
   把上游状态原样带进证据；不静默跳过，也不改口说"未执行"。
3. **离线。** 本模块不做网络调用；PC-06/PC-07 用离线替身传输，
   真实付费路径仍只走 `demo/provider/dashscope_i2i.py`。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import contracts as C
from . import packages as PKG
from . import prompt as P

ROOT = Path(__file__).resolve().parents[2]

for _p in (str(ROOT / "demo" / "fixture"), str(ROOT / "demo" / "provider")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dashscope_i2i as I2I      # noqa: E402
import factcard                  # noqa: E402
import pack_tools                # noqa: E402

# 商品身份与商品资产位置全部在**调用时**由包解析器解析（§4.6 硬规矩 1）：
# 这里一个路径常量都不留 —— 导入时把默认包焊死，换商品就等于改 .py。
SLOTS_REL = "config/slots.yaml"


def card_sub(project=ROOT, sku=None) -> str:
    """默认商品包的事实卡相对路径（调用时解析；给定 sku 就解析那个包）。"""
    return PKG.sub_of(project, "card", sku)


def refpack_of(project=ROOT, sku=None) -> dict:
    """本商品用哪个冻结参考包 —— 由商品包里的 reference_pack.json 声明。"""
    return PKG.refpack_of(project, sku)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_id(obj) -> str:
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ PC-01
def intake(project=ROOT, sku=None) -> C.StepResult:
    """PC-01 素材接入：只读校验参考包，产出 ReferencePackVersion。

    参考包由商品包声明，所以换商品时这一步同样只换数据：入口接受商品 id 或包路径。
    """
    project = Path(project)
    try:
        ref = PKG.refpack_of(project, sku)
    except PKG.PackageError as exc:               # 缺料要报缺料，不拿别的商品的参考包顶上
        return C.StepResult("PC-01", "business_reject",
                            payload={"sku": sku, "reason": "missing_package_data"},
                            notes=[str(exc)])
    man_path = ref["manifest"]
    try:
        code, report = pack_tools.verify(project, pack_sub=ref["pack_dir"])
    except Exception as exc:                      # 校验器自己炸了 ≠ 素材不合格
        return C.StepResult("PC-01", "technical_fail",
                            evidence={"exception": f"{type(exc).__name__}: {exc}"},
                            notes=["素材校验器自身失败；这是工具问题，不是素材问题"])
    if code != 0:
        return C.StepResult("PC-01", "business_reject",
                            payload={"pack_verify_exit": code}, evidence=report,
                            notes=["参考包未通过齐套检查（缺文件或哈希漂移）；"
                                   "补齐或恢复原文件后才能继续，不许就地改写素材来过检"])
    manifest = json.loads(man_path.read_text(encoding="utf-8"))
    views = manifest.get("views") or []
    refpack = {
        "pack_id": sha256_file(man_path),
        "sku": ref["sku"],
        "pack_dir": ref["pack_dir"],
        "declared_in": ref["source"],
        "manifest": man_path.relative_to(project).as_posix(),
        "views": [{"view_id": v["view_id"], "role": v.get("role"), "file": v["file"],
                   "sha256": v["sha256"], "order": i} for i, v in enumerate(views)],
        "order": [v["view_id"] for v in views],
        "disclaimer": manifest.get("disclaimer"),
    }
    unknown_role = [v["view_id"] for v in refpack["views"] if not v["role"]]
    if unknown_role:
        return C.StepResult("PC-01", "unknown", payload=refpack, evidence=report,
                            notes=[f"这些视图没有角色说明：{unknown_role}；"
                                   f"需要用户确认它们能否作为参考图使用"])
    return C.StepResult("PC-01", "accepted", payload=refpack, evidence=report,
                        notes=[f"参考包齐套：{len(refpack['views'])} 个视图，逐文件哈希与 manifest 一致"])


# ------------------------------------------------------------------ PC-02
def fact_problems(card: dict) -> tuple[list[str], list[str]]:
    """PC-02 的全部规则只在这里。返回 (problems, unknown_fields)。

    抽成独立函数有两个理由：规则可以被人一眼读全；反例与变异测试可以只替换这一处，
    从而证明「判据确实有牙」——如果把它压在日常流程里，就没有办法只削弱它一次。
    """
    unknown_fields = [u.get("field") for u in (card.get("unknowns") or []) if u.get("field")]
    problems: list[str] = []
    for fact in card.get("facts") or []:
        fid = fact.get("id")
        has_machine = bool(fact.get("machine_checks"))
        has_human = bool((fact.get("human_note") or "").strip())
        if not (has_machine or has_human):
            problems.append(f"{fid}: 既没有 machine_checks 也没有 human_note —— 这是一条无依据断言")
        if fact.get("modality") == "machine":
            hit = [u for u in unknown_fields if u in (fact.get("claim") or "")]
            if hit:
                problems.append(f"{fid}: 用 machine 模态断言了未确认字段 {hit} —— "
                                f"机器证据只能覆盖看得见的性质（材质/容量/保温性能必须保持 Unknown）")
    if not unknown_fields:
        problems.append("事实卡没有登记任何 Unknown 字段 —— "
                        "未声明的字段会以「已确认」的姿态流进计划和提示词")
    return problems, unknown_fields


def facts(project=ROOT, refpack=None, *, sku=None) -> C.StepResult:
    """PC-02 ProductFacts：把事实卡变成带来源的 FactsVersion。

    事实卡来自**调用时解析的商品包**：给定 sku 就读那个包，不给就取默认包。
    """
    project = Path(project)
    try:
        card_rel = PKG.sub_of(project, "card", sku)
    except PKG.PackageError as exc:               # 缺料要报缺料
        return C.StepResult("PC-02", "business_reject",
                            payload={"sku": sku, "reason": "missing_package_data"},
                            notes=[str(exc)])
    card_path = project / card_rel
    if not card_path.is_file():
        return C.StepResult("PC-02", "business_reject", payload={"card": card_rel},
                            notes=["缺事实卡；没有事实来源就不许往下编计划"])
    try:
        card = factcard.load_card(card_path)
        factcard.validate_card(card)
    except Exception as exc:
        return C.StepResult("PC-02", "business_reject",
                            evidence={"exception": f"{type(exc).__name__}: {exc}"},
                            notes=["事实卡不符合 schema；修卡而不是放宽校验"])

    problems, unknown_fields = fact_problems(card)
    if problems:
        return C.StepResult("PC-02", "business_reject",
                            evidence={"card": card_rel, "problems": problems},
                            notes=["事实层不通过：" + "；".join(problems[:3])])

    card_sha = sha256_file(card_path)
    facts_list = []
    for fact in card["facts"]:
        facts_list.append({
            "id": fact["id"],
            "claim": fact["claim"],
            "modality": fact["modality"],
            "machine_checks": fact.get("machine_checks") or [],
            "human_note": fact.get("human_note"),
            "violation": fact.get("violation"),
            "source": {"kind": "fact_card", "ref": card_rel, "sha256": card_sha},
            "confirmed_by": ("fixture_fact_card" if fact.get("modality") == "machine"
                             else "pending_human"),
        })
    unresolved = [f["id"] for f in facts_list if f["modality"] != "machine"]
    version = {
        "card": card_rel,
        "card_sha256": card_sha,
        "card_version": card.get("version"),
        "identity": card.get("identity"),
        "palette": card.get("palette"),
        "facts": facts_list,
        "unknowns": card.get("unknowns") or [],
        "unresolved_facts": unresolved,
        "reference_pack_id": (refpack or {}).get("pack_id"),
    }
    version["facts_version"] = content_id({k: v for k, v in version.items() if k != "reference_pack_id"})
    return C.StepResult("PC-02", "accepted", payload=version,
                        evidence={"card_sha256": card_sha, "unknown_fields": unknown_fields},
                        notes=[f"{len(facts_list)} 条事实；{len(unresolved)} 条需要人工侧确认，"
                               f"{len(unknown_fields)} 个字段保持 Unknown"])


# ------------------------------------------------------------------ PC-03
SHOT_TEMPLATES = (
    {"shot_id": "S1", "platform_slot": "main", "purpose": "主图：纯白底、完整商品、无文字",
     "scene_id": "studio-white", "composition_id": "studio-centered",
     "reference_views": ["front-full"], "allowed_variation": ["lighting", "composition"]},
    {"shot_id": "S2", "platform_slot": "scene", "purpose": "场景图：真实使用场景中保持商品外观",
     "scene_id": "kitchen-lifestyle", "composition_id": "three-quarter-hero",
     "reference_views": ["front-full"], "allowed_variation": ["scene", "lighting", "composition"]},
    {"shot_id": "S3", "platform_slot": "detail", "purpose": "细节图：杯盖与装饰环",
     "scene_id": "studio-white", "composition_id": "studio-centered",
     "reference_views": ["upper-closeup"], "allowed_variation": ["lighting", "composition"]},
    {"shot_id": "S4", "platform_slot": "detail", "purpose": "细节图：防滑套与底部",
     "scene_id": "studio-white", "composition_id": "studio-centered",
     "reference_views": ["lower-detail"], "allowed_variation": ["lighting", "composition"]},
)


def platform_rules(project=ROOT) -> dict:
    """平台规则只从 `config/slots.yaml` 读 —— 不在代码里另写一套平台语义。"""
    import yaml
    doc = yaml.safe_load((Path(project) / SLOTS_REL).read_text(encoding="utf-8"))
    return {"source": SLOTS_REL, "site": doc.get("site"), "export": doc.get("export") or {},
            "slot_roles": [s.get("role") for s in (doc.get("slots") or [])]}


def claim_problems(claims, fact_ids, unknown_fields) -> list[str]:
    """PC-03 的卖点规则只在这里：没有事实来源的卖点不许进计划。"""
    problems: list[str] = []
    for claim in claims:
        text = claim.get("text") or ""
        hit = [u for u in unknown_fields if u in text]
        if hit:
            problems.append(f"卖点「{text}」落在未确认字段 {hit} 上 —— "
                            f"没有事实来源的卖点不许进计划")
        if not (claim.get("facts") or []):
            problems.append(f"卖点「{text}」没有指向任何已确认事实")
        else:
            missing = [f for f in claim["facts"] if f not in fact_ids]
            if missing:
                problems.append(f"卖点「{text}」指向了不存在的事实 {missing}")
    return problems


def propose_plan(facts_version, refpack, platform, *, goal=None, confirmed_by=None) -> C.StepResult:
    """PC-03 图片计划：规则提案 + 确定性校验 + 用户确认后才冻结。"""
    fact_ids = {f["id"] for f in facts_version["facts"]}
    view_ids = set(refpack["order"])
    unknown_fields = [u["field"] for u in facts_version.get("unknowns") or [] if u.get("field")]
    problems: list[str] = []

    shots = []
    for tpl in SHOT_TEMPLATES:
        shot = dict(tpl)
        shot["must_preserve"] = sorted(fact_ids)
        if shot["platform_slot"] not in platform["slot_roles"]:
            problems.append(f"{shot['shot_id']}: 平台里没有这个坑位角色 {shot['platform_slot']!r}")
        missing_views = [v for v in shot["reference_views"] if v not in view_ids]
        if missing_views:
            problems.append(f"{shot['shot_id']}: 参考包里没有这些视图 {missing_views}")
        shots.append(shot)

    problems.extend(claim_problems((goal or {}).get("claims") or [],
                                   fact_ids, unknown_fields))

    if problems:
        return C.StepResult("PC-03", "business_reject",
                            evidence={"problems": problems, "platform": platform["source"]},
                            notes=["计划不通过：" + "；".join(problems[:3])])

    plan = {
        "task_goal": (goal or {}).get("text") or "为内置演示商品准备 Amazon US 上架图片",
        "platform": {"site": platform["site"], "export": platform["export"],
                     "source": platform["source"]},
        "shots": shots,
        "claims": (goal or {}).get("claims") or [],
        "facts_version": facts_version["facts_version"],
        "reference_pack_id": refpack["pack_id"],
        "confirmed_by": confirmed_by,
    }
    plan["plan_version"] = content_id({k: v for k, v in plan.items() if k != "confirmed_by"})

    if not confirmed_by:
        return C.StepResult("PC-03", "business_reject", payload=plan,
                            notes=["计划已生成但未经用户确认；确认前不冻结、不进入提示词编译"])
    return C.StepResult("PC-03", "accepted", payload=plan,
                        evidence={"shots": [s["shot_id"] for s in shots],
                                  "platform": platform["source"]},
                        notes=[f"{len(shots)} 张图，全部来自已确认事实与已登记坑位；"
                               f"由 {confirmed_by} 确认"])


# ------------------------------------------------------------------ PC-04
def style_spec(plan_version, facts_version, *, preferences=None, style_id="default",
               project=ROOT, sku=None) -> C.StepResult:
    """PC-04 视觉方向：可变审美与不可变事实锁分开，且可变项是白名单。"""
    profile = P.load_profile(project=project, sku=sku)
    spec = {"style_id": style_id, "variables": dict(preferences or {}),
            "locks": sorted(f["id"] for f in facts_version["facts"]),
            "source": "user_preferences" if preferences else "default"}
    try:
        resolved = P.resolve_style_variables(profile, spec)
    except P.PromptCompileError as exc:
        return C.StepResult("PC-04", "business_reject", payload=spec,
                            notes=[str(exc)])
    spec["variables"] = resolved
    spec["allowed_variations"] = list(profile["allowed_variations"])
    spec["style_version"] = content_id(spec)
    return C.StepResult("PC-04", "accepted", payload=spec,
                        notes=["使用默认视觉方向，可调整" if not preferences
                               else f"按用户偏好调整 {sorted(resolved)}"])


# ------------------------------------------------------------------ PC-05
def compile_prompt(plan_version, facts_version, style, shot_id, *,
                   project=ROOT, sku=None) -> C.StepResult:
    """PC-05 提示词：数据驱动装配，展示文本即发送文本。

    profile 与事实卡同源：调用时按 project/sku 解析，不在导入时取默认商品。
    """
    shot = next((s for s in plan_version["shots"] if s["shot_id"] == shot_id), None)
    if shot is None:
        return C.StepResult("PC-05", "business_reject", payload={"shot_id": shot_id},
                            notes=[f"计划里没有这一张图：{shot_id}"])
    try:
        version = P.compile_prompt(profile=P.load_profile(project=project, sku=sku),
                                   facts_version=facts_version, shot=shot, style=style)
    except P.PromptCompileError as exc:
        return C.StepResult("PC-05", "business_reject", payload={"shot_id": shot_id},
                            notes=[str(exc)])
    return C.StepResult("PC-05", "accepted", payload=version,
                        evidence={"prompt_sha256": version["prompt_sha256"],
                                  "locks_facts": version["locks_facts"]},
                        notes=[f"{len(version['prompt_text'])} 字符，锁住 "
                               f"{len(version['locks_facts'])} 条事实；展示文本与发送文本同源"])


def edit_prompt(version, *, append=None, raw_text=None) -> C.StepResult:
    """PC-05 的编辑路径：结构化追加或原始文本编辑，都产出新版本并记父版本。"""
    try:
        if raw_text is not None:
            child = P.guard_raw_edit(version, raw_text)
        else:
            child = P.append_direction(version, append or "")
    except P.PromptCompileError as exc:
        return C.StepResult("PC-05", "business_reject",
                            payload={"parent": version.get("version_id")},
                            notes=[str(exc)])
    return C.StepResult("PC-05", "accepted", payload=child,
                        evidence={"parent": version["version_id"],
                                  "prompt_sha256": child["prompt_sha256"],
                                  "diff": child["diff"]},
                        notes=[f"新版本 {child['version_id'][:12]}…；父版本 "
                               f"{version['version_id'][:12]}… 保持不变"])


# ------------------------------------------------------------------ PC-06 / PC-07
def resolve_references(project, refpack, view_ids):
    project = Path(project)
    by_id = {v["view_id"]: v for v in refpack["views"]}
    missing = [v for v in view_ids if v not in by_id]
    if missing:
        raise KeyError(f"参考包里没有视图 {missing}")
    return [project / by_id[v]["file"] for v in view_ids]


def submit(*, prompt_version, reference_paths, store_dir, ledger_path, seed,
           shot, transport=None, api_key="offline-fake", size=None,
           budget_limit=None, project=ROOT) -> C.StepResult:
    """PC-06 生成提交：预算/去重/守卫都在发请求之前。"""
    store = I2I.AttemptStore(store_dir)
    ledger = I2I.Ledger(ledger_path)
    size = size or I2I.DEFAULT_SIZE

    if budget_limit is not None:
        spent = len(ledger.records())
        if spent + 1 > budget_limit:
            return C.StepResult("PC-06", "business_reject",
                                evidence={"spent": spent, "limit": budget_limit},
                                notes=[f"预算已用 {spent}/{budget_limit}，不再提交；"
                                       f"扩大预算需要新的授权"])
    try:
        provider = I2I.Provider(store=store, ledger=ledger, transport=transport,
                                api_key=api_key)
        result = provider.submit(prompt=prompt_version["prompt_text"],
                                 references=reference_paths, seed=seed, size=size,
                                 negative_prompt=prompt_version["negative_prompt"],
                                 n=1, prompt_extend=False, watermark=False,
                                 poll_timeout_s=shot.get("poll_timeout_s", 2),
                                 poll_interval_s=0.05)
    except I2I.ProviderGuardError as exc:
        return C.StepResult("PC-06", "business_reject",
                            notes=[f"提交前守卫拒绝：{exc}"])
    except Exception as exc:
        return C.StepResult("PC-06", "technical_fail",
                            evidence={"exception": f"{type(exc).__name__}: {exc}"},
                            notes=["提交过程出现技术故障；这不等于没花钱，需按 action id 核对"])

    status = result.get("status")
    base = {k: result.get(k) for k in ("action_id", "task_id", "request_sha256",
                                       "prompt_sha256", "reference_sha256", "seed", "size",
                                       "image_path", "image_sha256", "input_image_count")}
    if status == "SUCCEEDED":
        return C.StepResult("PC-06", "accepted", payload=base,
                            evidence={"status": status, "image_sha256": result.get("image_sha256"),
                                      "input_image_count": result.get("input_image_count")},
                            notes=["服务端回执成功；候选文件已落盘，未覆盖旧产物"])
    if status in ("UNKNOWN", "UNKNOWN_PENDING_RECONCILE"):
        return C.StepResult("PC-06", "unknown", payload=base,
                            evidence={"status": status, "reason": result.get("reason")},
                            notes=["提交结果未知：先按 action id / task id 核对原任务，"
                                   "核对清楚之前不得重发"])
    if status in ("SKIPPED_HAS_RESULT", "REJECTED"):
        return C.StepResult("PC-06", "business_reject", payload=base,
                            evidence={"status": status, "reason": result.get("reason")},
                            notes=[f"没有产生新的付费动作（{status}）"])
    return C.StepResult("PC-06", "technical_fail", payload=base,
                        evidence={"status": status, "reason": result.get("reason")},
                        notes=[f"provider 终态 {status}"])


def reconcile(*, store, action_id) -> C.StepResult:
    """PC-07 结果核对：只核对原任务，绝不因为"等太久"而重发。"""
    store = I2I.AttemptStore(store)
    if store.has_result(action_id):
        raw = store.raw_path(action_id)
        return C.StepResult("PC-07", "accepted",
                            payload={"action_id": action_id, "candidate": str(raw),
                                     "file_sha256": sha256_file(raw)},
                            notes=["原 task 终态为成功，候选文件与哈希已登记"])
    intent = store.read_intent(action_id) or {}
    status = intent.get("status")
    if status in ("submitting", "submitted", "unknown_submit", "unknown_poll"):
        return C.StepResult("PC-07", "unknown",
                            payload={"action_id": action_id, "task_id": intent.get("task_id"),
                                     "intent_status": status},
                            notes=["原任务尚未收尾：保留 task id，等 provider 侧可核对；"
                                   "核对清楚之前不得重发"])
    return C.StepResult("PC-07", "technical_fail",
                        payload={"action_id": action_id, "intent": intent},
                        notes=[f"没有可核对的产物，intent 状态={status!r}"])


# ------------------------------------------------------------------ 沙箱
def sandbox_project(source=ROOT, dest=None) -> Path:
    """把参考包复制到临时沙箱，供反例注入用（真实素材一个字节都不动）。"""
    dest = Path(dest) if dest else Path(tempfile.mkdtemp(prefix="front-chain-"))
    pack_tools._sandbox_copy(Path(source), dest)
    (dest / "config").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(source) / SLOTS_REL, dest / SLOTS_REL)
    return dest
