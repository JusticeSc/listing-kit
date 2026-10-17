#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V2 按影响选择验证：普通批次只跑受影响边界，完整集合仍可枚举。

为什么需要它
------------
CI verify job 与本地完整回归此前对所有变更跑同一套完整命令：
说明/纯布局的小改也要等全部浏览器，失败信息与真实风险不对齐。
本脚本不复制第二份命令清单：完整集合仍唯一由工作流 verify job 持有，
这里只按变更路径选择其中一个子集；选择失败/不可分类时走完整离线集合，
不允许静默空选通过。

选择规则（保守：宁可多跑，不漏风险）
----------------------------------
- 普通说明（`docs/**`、`_working/**`、根目录 `.md`）：控制面守卫
  （文档登记 / 项目状态 / 分类登记反例），状态与索引语义仍由这些守卫真跑；
  **只有**这类普通说明才算「不必跑浏览器」。`.md` 长在别处（`app/`、`src/`、
  `tools/`、`evals/`）不是说明文档，按未识别路径处理。
- 纯样式/布局（`.css` / `.html`）：受影响的真实页面消费者（UI2/UI3/6.4）。
- 领域规则/契约（`app/product_v2/domain/**`、`evals/product-v2/node/**`）：
  `npm test:domain`（速度快且是稳定行为资产）。
- TS/构建/产物：types + generated 全链；只改产物不同步时必须先 build 再提交。
- 前端业务（`app/product_v2/**` 的 js/ts、`workspace.js`、`storage/**`）、
  HTTP 入口（`app/server.py`、`app/product_v2_server.py`）、网关/Provider
  （`src/**`）、锁与依赖（`uv.lock`、`pyproject.toml`、`package*.json`）、
  验证策略（`.github/workflows/**`、`config/product-v2/verification.json`）：
  一律走**完整必要离线集合**。这些改动会改变真实用户结果或验证判据，
  挑一个小子集就是在用「少跑」换「假绿」。
- 跨组、未知路径、基线不可得：完整适用离线集合（paid/remote/manual 除外）。
- 容器/Dockerfile/发布链变更：container 相关行为仍按实际影响选择，不在本脚本静默跳过。

为什么执行前先验登记与命令清单
--------------------------
选择器只把登记当作「哪些模式属于付费/远程/聚合」的权威。登记读坏、schema 不对或
分类取值非法时，受限集合会静默变空 —— 于是付费模式会被当普通模式**跑起来**。
所以这里先验登记，再动手；验不过就明确失败（退出码 2），不拿「完整集合」兜底当没事。
同理，verify job 里出现命令解析器（`tools/check_verification.ci_commands`）还不认识的
新命令形态（例如 pytest 入口）时，选择器不静默少跑，而是明确失败并要求先扩展解析器。

退出码
----
0 = 选择成功（未 --run 时只打印）；2 = 登记/命令清单校验失败，或选择名在当前命令清单里
找不到（fail-closed：重命名/退出 CI 后不静默少跑）；
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()
sys.path.insert(0, str(ROOT / "tools"))
from check_verification import ci_commands  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "ci-cd.yml"
REGISTRY = ROOT / "config" / "product-v2" / "verification.json"

REGISTRY_SCHEMA = "amz-verification-registry/v1"
CATEGORIES = {"control", "types", "domain", "browser", "gateway", "paid", "remote", "aggregate"}
RESTRICTED_CATEGORIES = {"paid", "remote", "aggregate"}

INPUT_EXIT = 2

CONTROL = {
    "tools/check_docs.py",
    "tools/check_project_state.py",
    "tools/check_verification.py",
    "evals/probes/project_state.py",
    "evals/probes/docs_index.py",
    "evals/probes/verification_policy.py",
    "npm:check:versions",
}
LAYOUT = {
    "tools/verify_v2_ui_2_interaction_visual.py",
    "tools/verify_v2_ui_3_frontend.py",
    "tools/verify_v2_6_4_accessibility.py",
}
TYPES = {"npm:check:types", "npm:build:frontend"}
# 注：旧自研 emit 链（build_product_v2_ts.mjs / check:generated / jsconfig.json）已随 P4
# 标准 Vite 构建退役，当前权威（package.json/CI/tsconfig.json）不再有这些命令名；选择器
# 与真实命令清单一一对应，不保留退役名。

# 路径分类表（顺序即优先级，见 classify）。
LOCK_NAMES = {"uv.lock", "pyproject.toml", "package.json", "package-lock.json", ".python-version"}
POLICY_NAMES = {".github/workflows/ci-cd.yml", "tsconfig.json", "vite.config.mjs"}
CONTROL_NAMES = {
    "tools/check_docs.py",
    "tools/check_project_state.py",
    "tools/check_verification.py",
    "tools/refactor_resume.py",
    "tools/select_v2_checks.py",
}
DOC_PREFIXES = ("docs/", "_working/")
LAYOUT_SUFFIXES = (".css", ".html")
DOMAIN_PREFIXES = ("app/product_v2/domain/", "evals/product-v2/node/")
BUSINESS_PREFIXES = ("app/", "src/", "deploy/")
VERIFIER_PREFIXES = ("tools/", "evals/")


class SelectInputError(ValueError):
    """选择依赖（分类登记 / 命令清单）不可用：必须明确失败，不能静默全跑或空跑。"""


def classify(paths: list[str]) -> tuple[set[str], str]:
    """返回（所选命令的 entrypoint 前缀集合，选择理由）。空集 = 完整离线集合。"""
    if not paths:
        return set(), "没有可识别的变更路径：走完整离线集合"
    kinds: set[str] = set()
    for path in paths:
        name = path.replace("\\", "/")
        if name in LOCK_NAMES or name in POLICY_NAMES or name.startswith("config/product-v2/"):
            kinds.add("full")        # 依赖锁与验证策略：判据本身变了，必须全跑
        elif name.endswith(".md"):
            # 只有说明类路径才算「不必跑浏览器」；别处的 .md 不是文档。
            kinds.add("docs" if name.startswith(DOC_PREFIXES) or "/" not in name else "full")
        elif name.endswith(LAYOUT_SUFFIXES):
            kinds.add("layout")      # 纯呈现
        elif name.startswith(DOMAIN_PREFIXES):
            kinds.add("domain")      # 领域规则：受影响 node 用例
        elif name.startswith(BUSINESS_PREFIXES):
            kinds.add("full")        # 前端业务 / HTTP 入口 / 网关 Provider / 构建（含业务 .ts，不只跑 types）
        elif name in CONTROL_NAMES:
            kinds.add("control")
        elif name.startswith(VERIFIER_PREFIXES):
            kinds.add("full")        # 验证器/探针自身：完整离线集合
        elif name.endswith(".ts"):
            kinds.add("types")       # 非业务 TS/构建/产物：types 全链
        else:
            kinds.add("unknown")

    if kinds <= {"docs"}:
        return set(CONTROL), "仅普通说明变更：控制面守卫（状态/索引语义仍跑对应检查）"
    if kinds <= {"docs", "layout"}:
        return set(CONTROL) | LAYOUT, "纯说明/布局变更：控制面 + 真实页面布局消费者"
    if "full" in kinds or "unknown" in kinds or len(kinds - {"docs", "layout"}) > 2:
        return set(), "业务/HTTP/网关/锁/验证策略/跨组或未知变更：走完整适用离线集合"

    selected: set[str] = set(CONTROL)
    if "types" in kinds:
        selected |= TYPES
    if "domain" in kinds:
        selected |= {"npm:test:domain"}
    if "control" in kinds:
        selected |= CONTROL
    if "layout" in kinds:
        selected |= LAYOUT
    return selected, "按变更影响选择：" + "、".join(sorted(kinds))


def load_commands(workflow: Path) -> list[tuple[str, list[str]]]:
    """读命令清单权威（工作流 verify job）；读不到或为空都不算通过。"""
    try:
        commands = ci_commands(workflow)
    except OSError as error:
        raise SelectInputError(f"命令清单权威读不到：{workflow}（{type(error).__name__}: {error}）") from error
    except (ValueError, KeyError, TypeError) as error:
        raise SelectInputError(f"命令清单权威解析失败：{workflow}（{type(error).__name__}: {error}）") from error
    if not commands:
        raise SelectInputError(f"命令清单为空：{workflow} 的 verify job 里没有可执行命令 —— 空集合不是通过")
    return commands


def load_restricted(registry: Path) -> set[tuple[str, tuple[str, ...]]]:
    """读分类登记并校验形状，返回 (入口, args) 的受限模式集合。

    登记坏掉时受限集合会静默为空，付费/远程模式于是被当成普通模式执行 ——
    所以这里宁可明确失败，也不返回一个「看起来正常」的空集合。
    """
    try:
        document = json.loads(registry.read_text(encoding="utf-8"))
    except OSError as error:
        raise SelectInputError(f"分类登记读不到：{registry}（{type(error).__name__}: {error}）") from error
    except ValueError as error:
        raise SelectInputError(f"分类登记不是合法 JSON：{registry}（{error}）") from error
    if not isinstance(document, dict) or document.get("schema") != REGISTRY_SCHEMA:
        raise SelectInputError(f"分类登记 schema 不是 {REGISTRY_SCHEMA}：{registry}")
    entries = document.get("entrypoints")
    if not isinstance(entries, dict) or not entries:
        raise SelectInputError(f"分类登记没有 entrypoints：{registry}")
    restricted: set[tuple[str, tuple[str, ...]]] = set()
    for entrypoint, modes in entries.items():
        if not isinstance(modes, list) or not modes:
            raise SelectInputError(f"分类登记里入口没有模式：{entrypoint}")
        for mode in modes:
            if not isinstance(mode, dict):
                raise SelectInputError(f"分类登记里模式不是对象：{entrypoint}")
            args, category = mode.get("args"), mode.get("category")
            if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
                raise SelectInputError(f"分类登记里模式 args 不是字符串列表：{entrypoint}")
            if category not in CATEGORIES:
                raise SelectInputError(f"分类登记里模式分类取值非法：{entrypoint} category={category!r}")
            if category in RESTRICTED_CATEGORIES:
                restricted.add((entrypoint, tuple(args)))
    return restricted


def unparsed_verify_commands(workflow: Path, commands: list[tuple[str, list[str]]]) -> list[str]:
    """verify job 里提到 `.py`、但命令解析器没认出来的行。

    新命令形态（例如 pytest 入口）先进工作流、后扩展解析器时，选择器会只跑
    「认识的那部分」并判绿 —— 少跑的命令没有任何信号。这里把它变成显式失败，
    等解析器真的支持之后，这些行的 `.py` 会出现在已解析命令里，本检查自然不再命中。
    """
    known = {script.replace("\\", "/") for script, _ in commands}
    for _script, extra in commands:
        known |= {arg.replace("\\", "/") for arg in extra}
    flagged: list[str] = []
    try:
        document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        steps = document["jobs"]["verify"]["steps"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SelectInputError(f"命令清单权威解析失败：{workflow}（{type(error).__name__}: {error}）") from error
    for step in steps:
        for raw in str(step.get("run", "")).splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                tokens = shlex.split(line, comments=True)
            except ValueError:
                continue
            if any(token.endswith(".py") and token.replace("\\", "/") not in known for token in tokens):
                flagged.append(line)
    return flagged


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", help="变更路径（为空则走完整集合）")
    ap.add_argument("--run", action="store_true", help="实际执行所选命令，首个失败即停")
    ap.add_argument("--emit-github", action="store_true", help="输出 GitHub 可读的选择结果")
    ap.add_argument("--workflow", type=Path, default=WORKFLOW, help="命令清单权威（反例/烟测可换成夹具）")
    ap.add_argument("--registry", type=Path, default=REGISTRY, help="分类登记（反例/烟测可换成夹具）")
    args = ap.parse_args(argv)

    try:
        commands = load_commands(args.workflow)
        restricted = load_restricted(args.registry)
        flagged = unparsed_verify_commands(args.workflow, commands)
    except SelectInputError as error:
        print(f"[FAIL] SELECT-INPUT {error}")
        return INPUT_EXIT
    if flagged:
        print("[FAIL] SELECT-INPUT verify job 里有命令解析器还不认识的验证命令（提到 .py 却未被解析）：")
        for line in flagged:
            print(f"       {line}")
        print("       先扩展命令解析器与登记，再选择 —— 静默跳过新命令等于少跑还判绿。")
        return INPUT_EXIT

    full = [(script, extra) for script, extra in commands
            if (script, tuple(extra)) not in restricted]
    if not full:
        print("[FAIL] SELECT-INPUT 完整离线集合为空（命令清单里全是受限模式）—— 不静默判绿。")
        return INPUT_EXIT

    wanted, reason = classify(args.paths)
    selected = full if not wanted else [item for item in full if item[0] in wanted]
    # 防呆：选择器永远不允许输出空集合；分类失败/无命中时回到完整集合。
    if not selected:
        selected = full
        if wanted:
            reason += "；所选集合为空，已回退到完整离线集合"
    # 选择名在当前命令清单里找不到时，必须显式说出来（重命名/退出 CI 后不能静默少跑）。
    unresolved = sorted(wanted - {script for script, _ in full})
    if unresolved:
        print(("[FAIL] SELECT-INPUT 选择名不在当前命令清单里（可能已改名或退出 CI）："
               + "、".join(unresolved) + " —— 先同步分类表与真实命令，不静默少跑。")
              .encode("utf-8", "replace").decode("utf-8"))
        return INPUT_EXIT

    if args.emit_github:
        print(json.dumps({
            "reason": reason,
            "selected": [f"{script} {' '.join(extra)}".strip() for script, extra in selected],
            "full_count": len(full),
            "selected_count": len(selected),
            "unresolved": unresolved,
            "input_ok": True,
        }, ensure_ascii=False))
        return 0
    print(f"选择理由：{reason}".encode("utf-8", "replace").decode("utf-8"))
    print(f"完整离线集合 {len(full)} 条，本次选择 {len(selected)} 条"
          f"（受限 paid/remote/aggregate 模式 {len(restricted)} 条已排除）"
          .encode("utf-8", "replace").decode("utf-8"))
    if not args.run:
        return 0
    for script, extra in selected:
        if script.startswith("npm:"):
            npm = "npm.cmd" if sys.platform == "win32" else "npm"
            argv_cmd = [npm, "run", script[4:], *(["--", *extra] if extra else [])]
        elif script.startswith("pytest:"):
            argv_cmd = ["uv", "run", "--locked", "python", "-m", "pytest",
                        script[len("pytest:"):], *extra]
        else:
            argv_cmd = ["uv", "run", "--locked", "python", script, *extra]
        print(f"\n$ {' '.join(argv_cmd)}".encode("utf-8", "replace").decode("utf-8"))
        proc = subprocess.run(argv_cmd, cwd=str(ROOT))
        if proc.returncode != 0:
            print(f"首个失败即停：{script} 退出码 {proc.returncode}，不继续后续命令")
            return proc.returncode
    print("所选命令全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
