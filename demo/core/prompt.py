# -*- coding: utf-8 -*-
"""PC-05 提示词编译 —— 数据驱动，且必须能逐字重建已经发出去的那条提示词。

三条设计约束（都是被前面的返工逼出来的）：

1. **正文不在代码里。** 锁定段落的英文文本放在 profile（数据）里，代码只做装配。
   代码里写死一段 1985 字符的英文，就等于把「唯一有真实产出证据的提示词」
   变成一个只能靠人眼比对的字符串。

2. **可变项是白名单。** 只有 profile.allowed_variations 里登记的键能出现在
   风格变量里；`body_*` / `lid_*` / `material_*` 这类前缀属于事实锁，
   出现即拒绝。用黑名单挡「不许改颜色」永远挡不完。

3. **编辑不许静默删锁。** 结构化编辑（追加允许方向）产生新版本；
   原始文本编辑必须让每个「带锁的段」逐字保留，否则拒绝。
   少了这一段，用户改一句话就能把 F8「无文字」的约束删掉，而系统看不出来。

工具：compile_prompt / append_direction / guard_raw_edit / load_profile
退出语义由调用方（front_chain）翻译成合同结果；本模块只抛 PromptCompileError。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from pathlib import Path

from . import packages as PKG

ROOT = Path(__file__).resolve().parents[2]
# profile 来自商品包，**调用时**解析（§4.6 硬规矩 1）：模块级不留默认包路径常量。
# 调用方可以给 path，也可以给 sku；两条路都指向同一个解析器。

PROMPT_SCHEMA = "demo-prompt-version/1"


class PromptCompileError(RuntimeError):
    """业务拒绝：输入不满足编译前提（未知场景、缺事实锁、编辑删锁等）。"""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_profile(path=None, *, project=ROOT, sku=None) -> dict:
    path = Path(path) if path else PKG.path_of(project, "prompt_profile", sku)
    profile = json.loads(path.read_text(encoding="utf-8"))
    if profile.get("schema") != "amz-listing-kit/prompt-profile@1":
        raise PromptCompileError(f"profile schema 不认识：{profile.get('schema')!r}")
    for key in ("blocks", "scenes", "compositions", "allowed_variations",
                "negative_prompt", "style_key_policy"):
        if key not in profile:
            raise PromptCompileError(f"profile 缺字段：{key}")
    return profile


def resolve_style_variables(profile: dict, style: dict | None) -> dict:
    variables = dict((style or {}).get("variables") or {})
    allowed = set(profile["allowed_variations"])
    reserved = tuple(profile["style_key_policy"]["reserved_prefixes"])
    rejected = []
    for key in sorted(variables):
        if key in allowed:
            continue
        why = "属于事实锁前缀" if key.startswith(reserved) else "未登记为可变项"
        rejected.append(f"{key}（{why}）")
    if rejected:
        raise PromptCompileError(
            "风格变量里有不允许改的项：" + "、".join(rejected)
            + f"。可变项是白名单 {sorted(allowed)}，其余一律视为事实锁。")
    return variables


def compile_prompt(*, profile: dict, facts_version: dict, shot: dict,
                   style: dict | None = None) -> dict:
    """装配一个 PromptVersion。同一输入必须得到逐字节相同的产物。"""
    fact_ids = {f["id"] for f in facts_version.get("facts", [])}
    scene_id = shot.get("scene_id")
    composition_id = shot.get("composition_id")
    if scene_id not in profile["scenes"]:
        raise PromptCompileError(f"未登记的场景：{scene_id!r}")
    if composition_id not in profile["compositions"]:
        raise PromptCompileError(f"未登记的构图：{composition_id!r}")

    variables = resolve_style_variables(profile, style)

    blocks: list[dict] = []
    for spec in profile["blocks"]:
        slot = spec.get("slot")
        if slot == "scene":
            text = profile["scenes"][scene_id]["text"]
        elif slot == "composition":
            text = profile["compositions"][composition_id]["text"]
        else:
            text = spec["text"]
        blocks.append({"block": spec["block"], "locks": list(spec["locks"]), "text": text})

    if variables:
        # 追加到最后一个**无锁**段（可变段）；有锁段落一个字都不许动。
        target = next((b for b in reversed(blocks) if not b["locks"]), None)
        if target is None:
            raise PromptCompileError("profile 里没有无锁段落，风格变量无处安放")
        suffix = " Additional allowed direction: " + "; ".join(
            f"{k} = {v}" for k, v in sorted(variables.items())) + "."
        target["text"] = target["text"] + suffix

    locked = sorted({f for b in blocks for f in b["locks"]})
    missing = [f for f in locked if f not in fact_ids]
    if missing:
        raise PromptCompileError(f"锁定了 FactsVersion 里不存在的事实：{missing}")
    must = list(shot.get("must_preserve") or [])
    uncovered = [f for f in must if f not in locked]
    if uncovered:
        raise PromptCompileError(f"必须保持的事实没有被任何锁定段覆盖：{uncovered}")

    text = "\n\n".join(b["text"] for b in blocks)
    negative = profile["negative_prompt"]
    version = {
        "schema": PROMPT_SCHEMA,
        "prompt_text": text,
        "prompt_sha256": sha256_text(text),
        "negative_prompt": negative,
        "negative_prompt_sha256": sha256_text(negative),
        "blocks": blocks,
        "locks_facts": locked,
        "parent_version": None,
        "origin": "demo/core/prompt.py 编译器（profile 驱动）",
        "profile_version": profile["profile_version"],
        "shot_id": shot.get("shot_id"),
        "style_id": (style or {}).get("style_id"),
        "scene_id": scene_id,
        "composition_id": composition_id,
        "fact_card_sha256": facts_version.get("card_sha256"),
        "fact_card_version": facts_version.get("card_version"),
    }
    version["version_id"] = _content_id(version)
    return version


def _content_id(version: dict) -> str:
    """内容身份：只由真正影响发送内容的东西决定，不含 parent/origin。"""
    material = {
        "prompt_text": version["prompt_text"],
        "negative_prompt": version["negative_prompt"],
        "shot_id": version.get("shot_id"),
        "style_id": version.get("style_id"),
        "parent_version": version.get("parent_version"),
    }
    blob = json.dumps(material, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def diff_lines(old_text: str, new_text: str) -> dict:
    """行级差异摘要。用来让人看清"这次编辑到底改了什么"。"""
    diff = list(difflib.unified_diff(old_text.splitlines(), new_text.splitlines(),
                                     lineterm="", n=1))
    return {"added": [l[1:] for l in diff if l.startswith("+") and not l.startswith("+++")],
            "removed": [l[1:] for l in diff if l.startswith("-") and not l.startswith("---")],
            "unified": diff}


def _as_child(base: dict, text: str, negative: str | None, *, origin: str) -> dict:
    child = {k: v for k, v in base.items() if k not in ("version_id",)}
    child["prompt_text"] = text
    child["prompt_sha256"] = sha256_text(text)
    if negative is not None:
        child["negative_prompt"] = negative
        child["negative_prompt_sha256"] = sha256_text(negative)
    child["parent_version"] = base["version_id"]
    child["origin"] = origin
    child["diff"] = diff_lines(base["prompt_text"], text)
    child["version_id"] = _content_id(child)
    return child


def append_direction(version: dict, sentence: str, *, origin: str = "用户追加允许方向") -> dict:
    """结构化编辑：只往**无锁段**追加一句话，锁定段保持逐字不变。"""
    sentence = (sentence or "").strip()
    if not sentence:
        raise PromptCompileError("追加内容为空 —— 空编辑不许产生新版本")
    blocks = [dict(b, locks=list(b["locks"])) for b in version["blocks"]]
    target = next((b for b in reversed(blocks) if not b["locks"]), None)
    if target is None:
        raise PromptCompileError("没有无锁段可追加")
    target["text"] = target["text"] + " " + sentence
    text = "\n\n".join(b["text"] for b in blocks)
    child = _as_child(version, text, None, origin=origin)
    child["blocks"] = blocks
    return child


def guard_raw_edit(version: dict, new_text: str, *, origin: str = "用户原始文本编辑") -> dict:
    """原始文本编辑：每个带锁段必须**逐字**仍在文本里，否则拒绝。"""
    missing = []
    for block in version["blocks"]:
        if block["locks"] and block["text"] not in new_text:
            missing.append(f"{block['block']}（锁 {block['locks']}）")
    if missing:
        raise PromptCompileError(
            "编辑删除了锁定事实段：" + "、".join(missing)
            + "。这些段落承载商品事实，删除等于把事实锁悄悄拿掉。")
    if new_text.strip() == version["prompt_text"].strip():
        raise PromptCompileError("编辑后文本与原文一致 —— 不产生新版本")
    child = _as_child(version, new_text, None, origin=origin)
    child["blocks"] = [dict(b, locks=list(b["locks"])) for b in version["blocks"]]
    return child


def sent_text_matches(version: dict, body: dict) -> bool:
    """确认请求体里发出去的文本就是界面上展示的那一份。"""
    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)
        elif isinstance(node, str):
            yield node

    return version["prompt_text"] in set(walk(body))
