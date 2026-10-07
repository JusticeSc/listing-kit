#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V2.7.4 准备件：把 C1–C17 的**证据存在性**与**未闭合的门**机械汇总成一张表。

它回答的不是「产品完成了吗」——那是 V2.7.4 的审计结论，需要人看对象、条件、时点、来源、
结果与限制。它回答的是三个可机械核对的问题：

    ① 计划 §11 声明的每条通过线，引用的证据文件在不在？
    ② 同一个证据里能不能找到它该有的结论标记（例如「全过」「8/8」）？
    ③ 哪些条目还挂着人工门或外部条件（真实模型闭环、陌生人/产品发起人走查）？

**机械汇总不能冒充完成判定**：表里的 `evidence_present` 只说明「有证据」，不说明
「证据支持这条声明」。审计人仍要逐条读证据（对象、条件、时点、来源、结果、限制）。

用法：
    uv run --locked python tools/audit_v2_7_4_completion.py
证据：evals/product-v2/v2.7.4-completion-matrix-<时间戳>.md/.json
"""
from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

EVIDENCE_DIR = ROOT / "evals" / "product-v2"

# 每条：声明（计划 §11 的通过线）→ 证据（glob + 该文件里必须出现的标记）+ 未闭合的门。
# 门分两类：human（必须由人完成）与 external（依赖外部条件，例如上游账户可用）。
MATRIX: dict[str, dict] = {
    "C1": {"claim": "浏览器从空白状态启动（无服务器 recent、绝对路径、预填商品或历史候选）",
           "evidence": [("evals/product-v2/v2.ui.1-remote-entry-*-final*.txt", None),
                        ("evals/product-v2/remote-no-model-roundtrip-*.txt", "RN-01")],
           "gates": []},
    "C2": {"claim": "刷新、浏览器重开、服务器重启后业务对象和 Blob 恢复",
           "evidence": [("evals/product-v2/remote-no-model-roundtrip-*.txt", "RN-08"),
                        ("evals/product-v2/v2.1.1-indexeddb-*.txt", None),
                        ("evals/product-v2/remote-persistence-*.txt", None)],
           "gates": []},
    "C3": {"claim": "两个独立浏览器配置文件项目列表和 IndexedDB 不互相出现",
           "evidence": [("evals/product-v2/v2.1.2-project-home-*.txt", "V2.1.2-08"),
                        ("evals/product-v2/v2.ui.1-remote-entry-*-final*.txt", "Edge")],
           "gates": []},
    "C4": {"claim": "项目 ZIP 导出、清空、导入后对象与 Blob hash 一致",
           "evidence": [("evals/product-v2/v2.6.3-transfer-*-final*.txt", None),
                        ("evals/product-v2/remote-no-model-roundtrip-*.txt", "RN-07")],
           "gates": []},
    "C5": {"claim": "四类商品动态槽位和 Brief 有合理差异，无商品名/fixture 分支",
           "evidence": [("evals/product-v2/v2.2.4-category-generality-*.txt", None)],
           "gates": []},
    "C6": {"claim": "来源、置信、确认与异常可见；模型提议不能自动提交为事实",
           "evidence": [("evals/product-v2/v2.2.1-product-contracts-*.txt", None),
                        ("evals/product-v2/v2.2.3-intake-understanding-*.txt", None)],
           "gates": []},
    "C7": {"claim": "可新增、复制、删除、排序 Shot；条件依赖能精确阻断无依据任务",
           "evidence": [("evals/product-v2/v2.3.1-suite-registry-*.txt", None),
                        ("evals/product-v2/v2.3.2-suite-editor-*.txt", None)],
           "gates": []},
    "C8": {"claim": "UI、PromptVersion、请求快照文本 hash 一致；语言策略明确",
           "evidence": [("evals/product-v2/v2.3.4-prompt-compiler-*-final*.txt", None),
                        ("evals/product-v2/v2.3.6-prompt-manual-edit-*-final*.txt", None)],
           "gates": []},
    "C9": {"claim": "qwen 请求含真实参考图和 task ID；候选非 Mock 并存为浏览器 Blob",
           "evidence": [("evals/product-v2/v2.4.5-live-reference-*-final*.txt", None),
                        ("evals/product-v2/v2.7.2-remote-real-e2e-*.txt", "RR-04")],
           "gates": []},
    "C10": {"claim": "双击、部分失败、刷新、服务重启、Unknown 不丢成功、不静默重复提交",
            "evidence": [("evals/product-v2/v2.4.2-generation-attempt-*-final*.txt", None),
                         ("evals/product-v2/v2.4.3-batch-suite-*-final*.txt", None),
                         ("evals/product-v2/v2.5.4-rework-loop-*final*.txt", None)],
            "gates": []},
    "C11": {"claim": "每候选有当前报告；异常优先；VLM Unknown/误判不自动采纳或硬拒绝",
            "evidence": [("evals/product-v2/v2.5.1-deterministic-review-*-final*.txt", None),
                         ("evals/product-v2/v2.5.2-vlm-review-*final*.txt", None)],
            "gates": []},
    "C12": {"claim": "旧候选保留；只目标 Shot 新增版本；无关 Attempt/Blob hash 不变",
            "evidence": [("evals/product-v2/v2.5.4-rework-loop-*final*.txt", None)],
            "gates": []},
    "C13": {"claim": "全部必需 Shot 恰一选择；ZIP manifest 可反查输入到候选",
            "evidence": [("evals/product-v2/v2.6.1-selection-*final*.txt", None),
                         ("evals/product-v2/v2.6.2-delivery-*-final*.txt", None)],
            "gates": []},
    "C14": {"claim": "非内置商品无需修改代码或夹具完成任务",
            "evidence": [("evals/product-v2/v2.2.4-category-generality-*.txt", None),
                         ("evals/product-v2/v2.7.2-remote-real-e2e-*.txt", "RR-03")],
            "gates": []},
    "C15": {"claim": "无命令行、JSON、开发者口授完成完整任务；介入为零",
            "evidence": [],
            "gates": ["human:V2.7.3 陌生人走查（含观察表与录屏）"]},
    "C16": {"claim": "可信 HTTPS origin；Chrome/Edge 空白创建、刷新、关页重开与服务重启后恢复",
            "evidence": [("evals/product-v2/v2.ui.1-remote-entry-*-final*.txt", None),
                         ("evals/product-v2/remote-no-model-roundtrip-*.txt", "RN-08")],
            "gates": []},
    "C17": {"claim": "首页与六阶段同页工作台通过产品发起人走查；图片优先、唯一主操作、渐进披露",
            "evidence": [("evals/product-v2/v2.ui.2-interaction-visual-*final*.txt", None),
                         ("evals/product-v2/v2.ui.3-frontend-*-final*.txt", None),
                         ("evals/product-v2/v2.6.4-a11y-*-final*.txt", None)],
            "gates": ["human:产品发起人走查（C17 的通过线里写明）"]},
}


@lru_cache(maxsize=1)
def tracked_evidence() -> frozenset[str]:
    """Only versioned evidence may feed a completion matrix.

    Local verifier output is useful while debugging, but a clean checkout cannot
    reproduce a matrix that points at an untracked newest file.
    """
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "evals/product-v2"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return frozenset()
    return frozenset(
        item.decode("utf-8").replace("\\", "/")
        for item in proc.stdout.split(b"\0") if item
    )


def newest(pattern: str) -> Path | None:
    tracked = tracked_evidence()
    hits = [
        p for p in EVIDENCE_DIR.glob("*")
        if fnmatch.fnmatch(p.name, pattern.split("/")[-1])
        and p.relative_to(ROOT).as_posix() in tracked
    ]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def verdict_ok(text: str, marker: str | None) -> bool:
    """一条证据算不算「通过的报告」：有 [PASS]、没有 [FAIL]/✗，且（若指定）含专属标记。

    为什么不用每条报告各自的「16/16」「11/11」：数字会随判据增删而变，写死就会误报；
    「至少一条 [PASS] + 零失败标记」才是这些验收报告的共同形态。专属标记只留给
    「必须证明某个具体子项」的条目（例如跨浏览器恢复要有 RN-07）。
    """
    return (text.count("[PASS]") > 0 and "[FAIL]" not in text and "✗" not in text
            and (marker is None or marker in text))


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows = []
    for item_id, spec in MATRIX.items():
        hits = []
        for pattern, marker in spec["evidence"]:
            path = newest(pattern)
            if path is None:
                hits.append({"pattern": pattern, "found": False, "marker_ok": False})
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            # 每条证据都要「有自己的结论标记」并且「没有失败标记」；具体标记由
            # MATRIX 里写（如 RN-08、11/11 通过），通用失败标记对所有条目生效。
            hits.append({"pattern": pattern, "found": True,
                         "file": path.relative_to(ROOT).as_posix(),
                         "marker": marker, "marker_ok": verdict_ok(text, marker)})
        evidence_ok = bool(hits) and all(h["found"] and h["marker_ok"] for h in hits)
        if not hits:
            state = ("human_pending" if any(g.startswith("human:") for g in spec["gates"])
                     else "no_evidence_declared")
        elif evidence_ok:
            state = "evidence_present"
        else:
            state = "evidence_broken"
        rows.append({"id": item_id, "claim": spec["claim"], "evidence": hits,
                     "evidence_present": evidence_ok, "state": state,
                     "gates_open": spec["gates"]})

    closed = [r for r in rows if r["evidence_present"] and not r["gates_open"]]
    broken = [r for r in rows if r["state"] == "evidence_broken"]
    with_evidence = [r for r in rows if r["evidence_present"]]
    open_gates = [(r["id"], g) for r in rows for g in r["gates_open"]]

    lines = [
        f"V2.7.4 完成矩阵（机械汇总） · {stamp}",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        "",
        "本表只核对「证据文件在不在、结论标记有没有」与「哪些门还开着」；",
        "**不判定 proven** —— 对象、条件、时点、来源、结果与限制仍要审计人逐条读。",
        "",
        f"证据齐备：{len(with_evidence)}/{len(rows)} · 无未闭合门且证据齐备：{len(closed)}/{len(rows)}",
        "",
    ]
    for row in rows:
        marks = "".join("✓" if h["found"] and h["marker_ok"] else "✗" for h in row["evidence"])
        state = {"evidence_present": "证据齐备", "evidence_broken": "证据坏了（缺失或含失败标记）",
                 "human_pending": "待人工门（尚未做）", "no_evidence_declared": "未声明证据"}[row["state"]]
        gates = "；".join(row["gates_open"]) or "无"
        lines.append(f"- {row['id']} [{state}] 证据 {marks or '（无声明）'} · 未闭合门：{gates}")
        lines.append(f"    通过线：{row['claim']}")
        for hit in row["evidence"]:
            if not hit["found"]:
                lines.append(f"    ✗ 找不到证据：{hit['pattern']}")
            elif not hit["marker_ok"]:
                lines.append(f"    ✗ {hit['file']} 里找不到标记 {hit['marker']!r}")
    lines += ["", "未闭合的门："]
    lines += [f"- {item_id}: {gate}" for item_id, gate in open_gates] or ["- （无）"]
    lines += ["", "BOUNDARY",
              "机械汇总；不替代 V2.7.4 审计结论，也不把「有证据」当成「已 proven」。"]

    out_md = EVIDENCE_DIR / f"v2.7.4-completion-matrix-{stamp}.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(json.dumps({"stamp": stamp, "rows": rows,
                                    "evidence_present": len(with_evidence),
                                    "closed": len(closed), "total": len(rows),
                                    "open_gates": open_gates},
                                   ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
    print("\n".join(lines[:8]))
    for item_id, gate in open_gates:
        print(f"  未闭合：{item_id} ← {gate}")
    print(f"证据：{out_md.relative_to(ROOT).as_posix()}")
    # 退出码只回答「声明的证据有没有坏」；Phase 7 还没走完不算这条命令的失败。
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
