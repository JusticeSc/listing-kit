#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""Data Policy v1 —— 外发动作的授权门（fail-closed）。

它回答的不是"能不能生成"，而是 **"这一份素材，能不能发给这个供应商、这个模型、
做这件事"**。只做判断：不生成图片、不持有密钥、不发请求、不写文件。

三条取舍（每条都有反向样本，见 `tools/verify_p1_2_policy.py`）：

  ① **默认放行是错的**。没命中一条写死的规则 → 按素材类别的 `default` 处理，
     而 `default` 只许是 `unapproved` 或 `denied`。默认 `allowed` 等于
     "忘了写就是批准"，而外发动作一旦发出去就收不回来。
  ② **通配不写**。规则键必须落到具体 `provider` + `model`。通配会让"哪一条说了算"
     变成运气，也会让"人像 / 竞品图必须单独授权"变成一句空话。
  ③ **过期按未批准处理**。`expires_at` 过了就是 `unapproved`，
     不是"打个警告继续发"。

还有一道独立的门：`signed_by` 为空时，规则表里写的 `allowed` **一条都不生效**
（一律 `unapproved` / `policy_not_signed`）。那一次签字就是计划 P1.2 的完成证据
"用户签署 allowlist"，不是装饰。

密钥不入库：加载时只要看到 key / secret / token / password 这类键，或看起来像密钥的
值（`sk-...`、PEM 头），直接报错拒绝加载。API key 走环境变量，文件进版本库。

版本：`policy_version = dpv1-<sha256(语义字段 canonical json) 前 12 位>`。
`updated_at` 不算语义字段（改个日期不该改授权版本），其余任何改动都会改版本 ——
于是"某次外发用的是哪一版授权"能事后对回来。

**光有版本号不够。** 答出"当时用的是哪一版"，不等于答得出"那一版写了什么"——
版本号是内容算出来的，内容一改就再也算不回旧号。所以每一版的**原文**存进
`contracts/data-policy-versions/<版本号>.yaml`（本项目没有版本库，只能自己存）。
写入归 `tools/sign_allowlist.py`；本模块只读，`read_archived()` 把某一版读回来。

用法：
    from data_policy import load_policy, PolicyDenied
    policy = load_policy()                       # 默认 contracts/data-policy-v1.yaml
    d = policy.decide(asset_class="product_reference", provider="供应商A",
                      model="模型X", purpose="reference_image_generation")
    if d.decision != "allowed":
        ...                                      # 本地/确定性路线照走，不许外发
    # 外发入口一律用这个（不许就抛，而不是"返回 False 让人自己记得检查"）：
    policy.require(asset_class=..., provider=..., model=..., purpose=...)
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "data-policy/v1"
DECISIONS = ("allowed", "denied", "unapproved")
# 类别默认值只许是这两个：`allowed` 不许当默认（默认放行 = 这道门不存在）
CLASS_DEFAULTS = ("unapproved", "denied")
DEFAULT_PATH = ROOT / "contracts" / "data-policy-v1.yaml"
# 每一版授权的内容存档目录（见模块头的"光有版本号不够"）。
VERSIONS_DIR = ROOT / "contracts" / "data-policy-versions"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SECRET_KEY_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|credential|authorization)")
_SECRET_VAL_RE = re.compile(r"(?i)^(sk|rk|pk|ghp|xox[baprs])[-_][A-Za-z0-9_\-]{12,}$")
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]+-----")


class PolicyError(Exception):
    """政策文件本身不合法 —— 加载即失败（fail-closed，不给"勉强能用"的余地）。"""


class PolicyDenied(Exception):
    """外发被拒。

    它**不等于技术失败**：这是门正常工作的结果，调用方应当走本地/确定性路线，
    并把 `.decision.reason` 一起记下来（谁被拦、为什么被拦，事后要能回答）。
    """

    def __init__(self, decision: "Decision") -> None:
        super().__init__(f"外发被拒：{decision.decision}"
                         f"（{decision.reason}，policy={decision.policy_version}）")
        self.decision = decision


@dataclass(frozen=True)
class Decision:
    """一次外发判断的完整结论。它本身就是审计记录的一行，所以带上全部依据。"""
    decision: str                 # allowed / denied / unapproved
    reason: str                   # 稳定短名，机器可归类
    policy_version: str           # dpv1-xxxxxxxxxxxx（当时用的是哪一版授权）
    asset_class: str
    purpose: str
    provider: str
    model: str
    rule_id: str | None = None
    approver: str | None = None
    approved_at: str | None = None
    expires_at: str | None = None
    retention: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ 版本

def semantic_doc(doc: dict) -> dict:
    """参与版本计算的字段：`updated_at` 除外（改个日期不该改授权版本）。"""
    return {k: v for k, v in doc.items() if k != "updated_at"}


def archive_path(version: str, *, root: Path | None = None) -> Path:
    return ((Path(root) if root else ROOT) / "contracts"
            / "data-policy-versions" / f"{version}.yaml")


def read_archived(version: str, *, root: Path | None = None) -> dict | None:
    """把某一版授权的原文读回来。读不到返回 None —— 算不算问题由调用方决定。

    存进去的是**语义字段**（不含 `updated_at`），所以把读回来的内容重新算一遍，
    必须得出文件名里那个版本号 —— 这是"存档没被就地改过"的判据。
    """
    import yaml
    p = archive_path(version, root=root)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def policy_version(doc: dict) -> str:
    """按**语义字段**算版本号：`updated_at` 不参与，其余任何改动都会变。"""
    semantic = semantic_doc(doc)
    # default=str：YAML 把没加引号的 2026-09-23 解析成 date 对象，
    # 而加了引号的是字符串 —— 两者必须是同一版授权，所以统一按 ISO 串算。
    blob = json.dumps(semantic, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str).encode("utf-8")
    return "dpv1-" + hashlib.sha256(blob).hexdigest()[:12]


def _iso(value) -> str | None:
    """决策对外一律给字符串：同一个日期不能一会儿是 date 一会儿是 str。"""
    if value is None:
        return None
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


def _as_date(value) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# ------------------------------------------------------------------ 校验

def _scan_secrets(node, path: str = "$") -> list[str]:
    """密钥不入库：键名或键值像凭证就报出来，并指出在哪条路径上。"""
    out: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            here = f"{path}.{k}"
            if _SECRET_KEY_RE.search(str(k)):
                out.append(f"{here}：键名像密钥/凭证 —— 密钥不入库，请走环境变量")
            out += _scan_secrets(v, here)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += _scan_secrets(v, f"{path}[{i}]")
    elif isinstance(node, str):
        if _SECRET_VAL_RE.match(node.strip()):
            out.append(f"{path}：值看起来像 API key（{node.strip()[:6]}…）—— 密钥不入库")
        elif _PEM_RE.search(node):
            out.append(f"{path}：值里带 PEM 私钥头 —— 密钥不入库")
    return out


def validate_policy(doc) -> list[str]:
    """不依赖 schema 库的轻量校验：够拦住"默认放行 / 没人批准就算批准 / 通配 / 密钥"。"""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["顶层不是映射"]
    for key in ("schema", "asset_classes", "purposes"):
        if key not in doc:
            problems.append(f"缺顶层键 {key}")
    if doc.get("schema") != SCHEMA:
        problems.append(f"schema 不是 {SCHEMA}")

    acs = doc.get("asset_classes")
    if not isinstance(acs, dict) or not acs:
        problems.append("asset_classes 必须是至少一个类别的映射")
        acs = {}
    for name, meta in acs.items():
        if not isinstance(meta, dict):
            problems.append(f"asset_classes.{name} 不是映射")
            continue
        d = meta.get("default")
        if d not in CLASS_DEFAULTS:
            problems.append(f"asset_classes.{name}.default={d!r} 不在 {CLASS_DEFAULTS} —— "
                            f"默认放行等于这道门不存在")
        if not str(meta.get("label") or "").strip():
            problems.append(f"asset_classes.{name} 缺 label —— 类别得有一句能读的说明")

    purs = doc.get("purposes")
    if not isinstance(purs, dict) or not purs:
        problems.append("purposes 必须是至少一个用途的映射")
        purs = {}

    sb, sa = doc.get("signed_by"), doc.get("signed_at")
    if sb is not None:
        if not str(sb).strip():
            problems.append("signed_by 是空串 —— 未签就写 null，别写空串")
        elif not _DATE_RE.match(str(sa or "")):
            problems.append("签了名就必须有 signed_at（YYYY-MM-DD）—— 谁在什么时候签的，是这次授权的依据")

    rules = doc.get("rules")
    if rules is None:
        rules = []
    if not isinstance(rules, list):
        problems.append("rules 必须是列表")
        rules = []
    seen_ids: set[str] = set()
    seen_keys: set[tuple] = set()
    for i, r in enumerate(rules):
        rid = str((r or {}).get("id") or "") if isinstance(r, dict) else ""
        where = f"rules[{i}]" + (f"({rid})" if rid else "")
        if not isinstance(r, dict):
            problems.append(f"{where} 不是映射")
            continue
        for key in ("id", "asset_class", "purpose", "provider", "model",
                    "decision", "retention"):
            if key not in r:
                problems.append(f"{where} 缺字段 {key}")
        if not rid:
            problems.append(f"{where} 的 id 是空的 —— 审计记录要靠它指回这条规则")
        elif rid in seen_ids:
            problems.append(f"{where} 的 id 重复：{rid}")
        else:
            seen_ids.add(rid)
        if r.get("asset_class") not in acs:
            problems.append(f"{where} 的 asset_class={r.get('asset_class')!r} "
                            f"不在 asset_classes 里：{sorted(acs)}")
        if r.get("purpose") not in purs:
            problems.append(f"{where} 的 purpose={r.get('purpose')!r} "
                            f"不在 purposes 里：{sorted(purs)}")
        for field in ("provider", "model"):
            v = str(r.get(field) or "").strip()
            if not v:
                problems.append(f"{where} 的 {field} 是空的 —— 键要落到具体值")
            elif v == "*":
                problems.append(f"{where} 的 {field} 用了通配 '*' —— 键必须落到具体值；"
                                f"通配会让'哪一条说了算'变成运气，也会让单独授权变成空话")
        dec = r.get("decision")
        if dec not in DECISIONS:
            problems.append(f"{where} 的 decision={dec!r} 不在取值域 {DECISIONS}")
        if dec == "allowed":
            if not str(r.get("approver") or "").strip():
                problems.append(f"{where} 是 allowed 却没有 approver —— 没人的批准不算批准")
            if not _DATE_RE.match(str(r.get("approved_at") or "")):
                problems.append(f"{where} 是 allowed 却没有 approved_at（YYYY-MM-DD）")
        if r.get("expires_at") is not None and not _DATE_RE.match(str(r["expires_at"])):
            problems.append(f"{where} 的 expires_at 不是 YYYY-MM-DD")
        if not str(r.get("retention") or "").strip():
            problems.append(f"{where} 缺 retention —— 说不清怎么保留/删除的授权，不算授权")
        key = (r.get("asset_class"), r.get("purpose"),
               str(r.get("provider") or "").strip(), str(r.get("model") or "").strip())
        if key in seen_keys:
            problems.append(f"{where} 与另一条规则的键完全一样 {key} —— 同一个键只能有一条规则，"
                            f"否则'哪一条说了算'要靠顺序碰运气")
        else:
            seen_keys.add(key)

    problems += _scan_secrets(doc)
    return problems


# ------------------------------------------------------------------ 加载与判断

class Policy:
    """一份加载好的政策。只读：`decide()` 不改传入对象、不写文件。"""

    def __init__(self, doc: dict, path: Path | None = None) -> None:
        self.doc = doc
        self.path = path
        self.policy_version = policy_version(doc)
        self.signed_by = _iso(doc.get("signed_by"))
        self.signed_at = _iso(doc.get("signed_at"))
        self._acs = dict(doc.get("asset_classes") or {})
        self._purposes = dict(doc.get("purposes") or {})
        self._rules = [r for r in (doc.get("rules") or []) if isinstance(r, dict)]

    def asset_classes(self) -> dict:
        return dict(self._acs)

    def purposes(self) -> dict:
        return dict(self._purposes)

    def rules(self) -> list[dict]:
        return list(self._rules)

    def decide(self, *, asset_class: str, provider: str, model: str,
               purpose: str, now=None) -> Decision:
        base = dict(policy_version=self.policy_version, asset_class=asset_class,
                    purpose=purpose, provider=provider, model=model)
        ac = self._acs.get(asset_class)
        if ac is None:
            return Decision(**base, decision="unapproved", reason="unknown_asset_class")
        if purpose not in self._purposes:
            return Decision(**base, decision="unapproved", reason="unknown_purpose")
        if not str(provider or "").strip() or not str(model or "").strip():
            return Decision(**base, decision="unapproved", reason="missing_provider_or_model")
        if not self.signed_by:
            # 清单还没被接受：规则表里写什么都按未批准处理。
            return Decision(**base, decision="unapproved", reason="policy_not_signed")

        rule = None
        for r in self._rules:
            if (r.get("asset_class") == asset_class and r.get("purpose") == purpose
                    and str(r.get("provider") or "").strip() == str(provider).strip()
                    and str(r.get("model") or "").strip() == str(model).strip()):
                rule = r
                break
        if rule is None:
            return Decision(**base, decision=ac.get("default"), reason="no_matching_rule")

        meta = dict(rule_id=str(rule.get("id")),
                    approver=_iso(rule.get("approver")), approved_at=_iso(rule.get("approved_at")),
                    expires_at=_iso(rule.get("expires_at")), retention=_iso(rule.get("retention")))
        dec = rule.get("decision")
        if dec == "allowed":
            # 缺批准人的 allowed 在加载时就被 validate_policy 拦下了，走不到这里；
            # 所以运行时只剩「过期」这一种时间性失效。
            exp = rule.get("expires_at")
            if exp and _as_date(now) > _as_date(exp):
                return Decision(**base, **meta, decision="unapproved", reason="expired")
            return Decision(**base, **meta, decision="allowed", reason="rule_allowed")
        if dec == "denied":
            return Decision(**base, **meta, decision="denied", reason="rule_denied")
        return Decision(**base, **meta, decision="unapproved", reason="rule_unapproved")

    def require(self, **kw) -> Decision:
        """外发入口用它：不许就抛，而不是"返回 False 让人自己记得检查"。"""
        d = self.decide(**kw)
        if d.decision != "allowed":
            raise PolicyDenied(d)
        return d


def load_policy(path: str | Path | None = None) -> Policy:
    import yaml                      # 只在加载时用得到，不拖累只查政策的调用方
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        raise PolicyError(f"找不到政策文件：{p}")
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    problems = validate_policy(doc)
    if problems:
        raise PolicyError("政策文件不合法：\n  - " + "\n  - ".join(problems))
    return Policy(doc, p)
