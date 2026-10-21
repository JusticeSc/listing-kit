#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按实际变更选择必要离线检查；命令目录唯一来自 CI verify job。

说明/过程证据只跑管理检查，单验证器选择自身，已知 UI owner 选择其业务消费者。
混合变化取并集；公共合同、依赖或未知影响保守扩大。没有批准离线模式的走查
明确报输入缺口，不能用跑完整产品集合代替验证走查本身。

执行前先验证整份命令目录的精确入口、参数与批准状态；paid/remote/aggregate
永不进入普通执行。登记不是用户授权，也不能拦截绕过本入口的动作。
无路径时枚举完整集合；--base/--head 按真实 Git 差量选择，坏基线退出 2。
--emit-github 只预览；--github-output 写 CI 路由；--run 首个失败即停。
--result-json 供 --run 输出机器可读原始执行凭据（实际argv/真实退出码/UTC时间/
选中与执行范围/源码快照）；只与 --run 配对，不与预览同用，不代签业务/像素。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shlex
import subprocess
import re
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

DOCS = {"tools/check_docs.py"}
POLICY = {"tools/check_verification.py", "evals/probes/verification_policy.py"}
STATE = DOCS | {"tools/check_project_state.py", "evals/probes/project_state.py"}
LAYOUT = {
    "tools/verify_v2_ui_2_interaction_visual.py",
    "tools/verify_v2_ui_3_frontend.py",
    "tools/verify_v2_6_4_accessibility.py",
}
FRONTEND = {
    "npm:check:versions", "npm:build:envelope", "npm:check:types",
    "npm:build:frontend", "npm:check:envelope", "npm:build:frontend-node",
}
UI_CONSUMERS = {
    "generation-view.ts": {
        # generation-view 独占 #task-list-mount 与 #shot-execution：凡通过这两个根
        # 读行状态/执行区动作的验证器都在这条依赖上，缺一个就是静默漏选。
        "tools/verify_v2_3_5_pre_generation_confirm.py",
        "tools/verify_v2_3_6_prompt_manual_edit.py",
        "tools/verify_v2_4_2_generation_attempt.py",
        "tools/verify_v2_4_3_batch_execution.py",
        "tools/verify_v2_4_4_candidate_blob.py",
        "tools/verify_v2_5_1_deterministic_review.py",
        "tools/verify_v2_5_2_vlm_review.py",
        "tools/verify_v2_5_3_compare_panel.py",
        "tools/verify_v2_5_4_rework_loop.py",
        "tools/verify_v2_5_5_suite_review.py",
        "tools/verify_v2_6_1_selection.py",
        "tools/verify_v2_6_3_project_transfer.py",
        "tools/verify_v2_packet08_adoption_ai.py",
        "tools/verify_v2_packet08_settings_vision.py",
        "tools/verify_v2_r5_2_two_adapters.py",
    },
    "compare-view.ts": {
        "tools/verify_v2_5_1_deterministic_review.py",
        "tools/verify_v2_5_2_vlm_review.py",
        "tools/verify_v2_5_3_compare_panel.py",
        "tools/verify_v2_5_4_rework_loop.py",
        "tools/verify_v2_6_1_selection.py",
    },
    "delivery-view.ts": {
        "tools/verify_v2_6_2_delivery.py",
        "tools/verify_v2_6_3_project_transfer.py",
        "tools/verify_v2_packet08_delivery_ai.py",
    },
    "input-view.ts": {
        "tools/verify_v2_2_1_product_contracts.py",
        "tools/verify_v2_2_3_intake_understanding.py",
        "tools/verify_v2_packet08_settings_vision.py",
    },
}
COMPARE_CONTRACT_INPUTS = {
    "config/product-v2/compare-contract.json",
    "evals/product-v2/harness/compare-panel.html",
    "evals/product-v2/harness/compare-panel.js",
    "tools/verify_v2_5_3_compare_panel.py",
}
LOCK_NAMES = {"uv.lock", "pyproject.toml", "package.json", "package-lock.json", ".python-version"}
POLICY_NAMES = {
    ".github/workflows/ci-cd.yml", "config/product-v2/verification.json",
    "tools/select_v2_checks.py", "tools/check_verification.py",
    "evals/probes/verification_policy.py",
}
BUILD_NAMES = {
    "Dockerfile", ".dockerignore", "vite.config.mjs", "tsconfig.json",
    "tools/export_image_envelope_schema.py", "tools/generate_image_envelope_validator.mjs",
}
PROOF_SUFFIXES = {".md", ".json", ".png", ".jpg", ".jpeg", ".webp", ".zip", ".log", ".txt", ".out"}
RESULT_SCHEMA = "amz-selector-result/v1"
# 快照只标识「测了哪棵树」，不证明语义正确/合格/可复用。
SNAPSHOT_DIRS = ("app", "src", "config", "tools", "tests", "deploy",
                 "evals/probes", "evals/product-v2/harness", "evals/product-v2/node",
                 "evals/product-v2/fixtures", "evals/product-v2/vendor", "dist/product-v2")
SNAPSHOT_ROOT_FILES = ("uv.lock", "pyproject.toml", "package.json", "package-lock.json",
                       ".python-version", "Dockerfile", ".dockerignore", "vite.config.mjs",
                       "tsconfig.json")
# 结果输出保护覆盖权威记录；不能把「源码快照范围」误当全部受保护文件。
RESULT_PROTECTED_DIRS = SNAPSHOT_DIRS + ("_working", "docs", ".github", ".git")
RESULT_PROTECTED_FILES = SNAPSHOT_ROOT_FILES + ("AGENTS.md", "README.md", ".gitattributes", ".gitignore")
SNAPSHOT_SKIP_DIRS = {"__pycache__", ".tmp", "node_modules", ".venv"}
SNAPSHOT_SKIP_SUFFIXES = (".pyc", ".pyo")


def snapshot_source(root: Path = ROOT) -> dict:
    """采集源码/构建输入快照：未提交改动可见，历史证据与临时夹具不计入。

    只在 --result-json 启用时调用；正常选择/预览/普通 --run 不走整树扫描。
    dist 只收 dist/product-v2 实际构建产物；其它 dist 输出一律不计入。
    """
    digests: dict[str, str] = {}
    for name in SNAPSHOT_ROOT_FILES:
        path = root / name
        if path.is_file():
            digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in SNAPSHOT_DIRS:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_dir():
                continue
            parts = path.relative_to(root).parts
            if any(part in SNAPSHOT_SKIP_DIRS for part in parts[:-1]):
                continue
            if path.suffix in SNAPSHOT_SKIP_SUFFIXES or path.name.startswith(".env"):
                continue
            if path.name.endswith(".local"):
                continue
            digests[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    digest_body = "".join(f"{name}\0{digests[name]}\0" for name in sorted(digests))
    return {
        "schema": "amz-source-snapshot/v1",
        "scope": {"dirs": list(SNAPSHOT_DIRS), "root_files": list(SNAPSHOT_ROOT_FILES)},
        "files": len(digests),
        "digest": hashlib.sha256(digest_body.encode("utf-8")).hexdigest(),
        "entries": digests,
    }


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def build_argv(script: str, extra: list[str]) -> list[str]:
    """所选模式的真实启动命令；与既有 --run 分支同一构造，不另建形态。"""
    if script.startswith("npm:"):
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        return [npm, "run", script[4:], *(["--", *extra] if extra else [])]
    if script.startswith("pytest:"):
        return ["uv", "run", "--locked", "python", "-m", "pytest", script[len("pytest:"):], *extra]
    return ["uv", "run", "--locked", "python", script, *extra]


def result_path_forbidden(result: Path, workflow: Path, registry: Path) -> str | None:
    """凭据不能覆盖源码、项目权威或仓库控制文件；无法确认路径安全也拒绝。"""
    try:
        resolved = result.resolve()
        workflow_resolved = workflow.resolve()
        registry_resolved = registry.resolve()
        root_resolved = ROOT.resolve()
    except OSError as error:
        return f"凭据路径无法安全解析：{result}（{error}）"
    if resolved == workflow_resolved:
        return f"凭据输出不能覆盖命令清单：{result}"
    if resolved == registry_resolved:
        return f"凭据输出不能覆盖分类登记：{result}"
    if any(resolved == root_resolved / name for name in RESULT_PROTECTED_FILES):
        return f"凭据输出不能覆盖源码或项目权威：{result}"
    if any(resolved.is_relative_to(root_resolved / name) for name in RESULT_PROTECTED_DIRS):
        return f"凭据输出不能覆盖源码或项目权威：{result}"
    return None


class SelectInputError(ValueError):
    """选择依赖（分类登记 / 命令清单）不可用：必须明确失败，不能静默全跑或空跑。"""


def classify(paths: list[str], available: set[str], registered: set[str]) -> tuple[set[str], str]:
    """空集表示完整离线集合；已知局部影响取并集，不因跨组自动全选。"""
    if not paths:
        return set(), "未指定差量：完整离线集合"
    wanted: set[str] = set()
    reasons: set[str] = set()
    broad = False
    for name in paths:
        if name in POLICY_NAMES:
            wanted |= POLICY
            reasons.add("验证策略")
        elif name in COMPARE_CONTRACT_INPUTS:
            wanted |= {"pytest:tests/dev", "tools/verify_v2_5_3_compare_panel.py"}
            reasons.add("比较合同及套件消费者")
        elif name in LOCK_NAMES or name in BUILD_NAMES or name.startswith("config/product-v2/"):
            broad = True
            reasons.add("公共构建/配置合同")
        elif name == "docs/INDEX.md" or name == "tools/check_docs.py":
            wanted |= DOCS | {"evals/probes/docs_index.py"}
            reasons.add("文档索引")
        elif name.endswith("/state.md") or name in {"docs/product-v2-refactor-plan.md", "tools/check_project_state.py", "tools/refactor_resume.py", "evals/probes/project_state.py"}:
            wanted |= STATE
            reasons.add("状态语义")
        elif name.startswith("docs/") and name.endswith(".md") or "/" not in name and name.endswith(".md"):
            wanted |= DOCS
            reasons.add("普通说明")
        elif name.startswith("_working/") and Path(name).suffix in PROOF_SUFFIXES:
            wanted |= DOCS
            reasons.add("工作记录")
        elif name.startswith(("evals/product-v2/node/", "app/product_v2/domain/")):
            wanted |= FRONTEND | {"npm:test:domain"}
            # 公共类型/序列化/聚合出口影响所有读写者，不能只用 Node 证明浏览器合同。
            broad |= Path(name).stem in {"index", "shared", "type-contracts", "types"}
            reasons.add("领域合同")
        elif name.startswith("app/product_v2/ui/") and Path(name).name in UI_CONSUMERS:
            # 任何视图改动都先过真实页面外观/交互/可达性三门，再叠加该视图的业务消费者。
            wanted |= FRONTEND | LAYOUT | UI_CONSUMERS[Path(name).name]
            reasons.add("页面业务消费者")
        elif name.startswith("app/product_v2/") and name.endswith((".css", ".html")):
            wanted |= FRONTEND | LAYOUT
            reasons.add("页面布局")
        elif name.startswith(("app/", "src/", "deploy/")):
            broad = True
            reasons.add("公共读写/出站消费者")
        elif name.startswith("tests/gateway/"):
            wanted.add("pytest:tests/gateway")
            reasons.add("网关测试")
        elif name.startswith("tests/dev/"):
            wanted |= FRONTEND | {"pytest:tests/dev"}
            reasons.add("开发工具测试")
        elif name in available:
            wanted.add(name)
            reasons.add("验证器自身")
        elif name.startswith("tools/verify_v2") or name.startswith("tools/rehearse_"):
            if name in registered or not (ROOT / name).exists():
                wanted |= POLICY
                reasons.add("受限/退役验证器登记维护（不执行该入口）")
            else:
                raise SelectInputError(f"{name} 没有登记的离线验证依据；需补齐素材/参数，不能用完整产品回归代替")
        elif (name.startswith(("_stage-amz-control/", "evals/product-v2/"))
              and not name.startswith(("evals/product-v2/harness/", "evals/product-v2/fixtures/"))
              and Path(name).suffix in PROOF_SUFFIXES):
            wanted |= DOCS
            reasons.add("不可执行过程证据")
        else:
            broad = True
            reasons.add("公共消费者或未知影响")
    return (set() if broad else wanted), "按影响选择：" + "、".join(sorted(reasons))


def container_affected(paths: list[str]) -> bool:
    """依据当前 Docker/发布闭包；codegen 与发布探针先于普通 tools 排除。"""
    for name in paths:
        if (name in LOCK_NAMES | BUILD_NAMES or name == ".github/workflows/ci-cd.yml"
                or name == "tools/release_transaction_probe.py"
                or name.startswith(("app/", "src/", "deploy/"))
                or name == "config/product-v2/providers.json"):
            return True
        if name == "config/product-v2/verification.json" or name in COMPARE_CONTRACT_INPUTS:
            continue
        if name.startswith(("docs/", "_working/", "_stage-amz-control/", "tools/", "evals/", "tests/")):
            continue
        if "/" not in name and name.endswith(".md"):
            continue
        return True  # 新的构建/发布输入尚未分类，不能误按证据-only 放行。
    return False


def changed_paths(base: str, head: str) -> list[str]:
    """只接受完整提交 SHA，读取新增/删除/重命名两端；坏基线不能变成空变更。"""
    if any(not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", value) for value in (base, head)):
        raise SelectInputError("--base/--head 必须是可读取的完整提交 SHA")
    result = subprocess.run(["git", "diff", "--name-only", "--no-renames", "-z", base, head, "--"],
                            cwd=ROOT, capture_output=True)
    if result.returncode:
        raise SelectInputError("Git 差量基线不可读取：" + result.stderr.decode("utf-8", "replace").strip())
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def load_commands(workflow: Path) -> list[tuple[str, list[str]]]:
    """读命令清单权威（工作流 verify job）；读不到或为空都不算通过。"""
    try:
        commands = ci_commands(workflow)
    except OSError as error:
        raise SelectInputError(f"命令清单权威读不到：{workflow}（{type(error).__name__}: {error}）") from error
    except (ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        raise SelectInputError(f"命令清单权威解析失败：{workflow}（{type(error).__name__}: {error}）") from error
    if not commands:
        raise SelectInputError(f"命令清单为空：{workflow} 的 verify job 里没有可执行命令 —— 空集合不是通过")
    return commands


def load_modes(registry: Path) -> dict[tuple[str, tuple[str, ...]], tuple[str, bool]]:
    """读取精确模式与批准状态；未知模式不能按「非受限」放行。"""
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
    modes_by_identity: dict[tuple[str, tuple[str, ...]], tuple[str, bool]] = {}
    for entrypoint, modes in entries.items():
        if not isinstance(modes, list) or not modes:
            raise SelectInputError(f"分类登记里入口没有模式：{entrypoint}")
        for mode in modes:
            if not isinstance(mode, dict):
                raise SelectInputError(f"分类登记里模式不是对象：{entrypoint}")
            args, category, ci = mode.get("args"), mode.get("category"), mode.get("ci")
            if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
                raise SelectInputError(f"分类登记里模式 args 不是字符串列表：{entrypoint}")
            if not isinstance(category, str) or category not in CATEGORIES:
                raise SelectInputError(f"分类登记里模式分类取值非法：{entrypoint} category={category!r}")
            if not isinstance(ci, bool):
                raise SelectInputError(f"分类登记里模式 ci 不是布尔值：{entrypoint}")
            identity = (entrypoint, tuple(args))
            if identity in modes_by_identity:
                raise SelectInputError(f"分类登记里精确模式重复：{identity}")
            if ci and category in RESTRICTED_CATEGORIES:
                raise SelectInputError(f"受限模式不得批准进入 CI：{identity}")
            modes_by_identity[identity] = (category, ci)
    return modes_by_identity


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
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
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
    ap.add_argument("--base", help="差量起点完整提交 SHA（与 --head 配对）")
    ap.add_argument("--head", help="差量终点完整提交 SHA")
    ap.add_argument("--github-output", type=Path, help="写入 GitHub job outputs（不执行检查）")
    ap.add_argument("--workflow", type=Path, default=WORKFLOW, help="命令清单权威（反例/烟测可换成夹具）")
    ap.add_argument("--registry", type=Path, default=REGISTRY, help="分类登记（反例/烟测可换成夹具）")
    ap.add_argument("--result-json", type=Path, default=None,
                    help="--run 的机器可读执行凭据输出路径（实际argv/真实退出码/UTC时间/范围/源码快照）")
    args = ap.parse_args(argv)
    if args.result_json is not None:
        if not args.run:
            print("[FAIL] SELECT-INPUT --result-json 只与 --run 配对：预览不产生执行凭据")
            return INPUT_EXIT
        if args.emit_github or args.github_output:
            print("[FAIL] SELECT-INPUT --result-json 不与预览同用：预览未执行，不能写执行凭据")
            return INPUT_EXIT
        forbidden_reason = result_path_forbidden(args.result_json, args.workflow, args.registry)
        if forbidden_reason is not None:
            print(f"[FAIL] SELECT-INPUT {forbidden_reason}")
            return INPUT_EXIT

    def write_result(document: dict) -> int | None:
        assert args.result_json is not None
        try:
            if args.result_json.exists() and args.result_json.is_dir():
                raise IsADirectoryError(f"凭据路径是目录：{args.result_json}")
            args.result_json.parent.mkdir(parents=True, exist_ok=True)
            args.result_json.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8", newline="\n")
        except OSError as error:
            print(f"[FAIL] SELECT-RESULT 凭据写失败：{args.result_json}（{error}）")
            return 1
        return None

    try:
        if bool(args.base) != bool(args.head) or args.base and args.paths:
            raise SelectInputError("--base/--head 必须配对，且不能同时指定 paths")
        paths = changed_paths(args.base, args.head) if args.base else args.paths
        paths = [path.replace("\\", "/").removeprefix("./") for path in paths]
        if any(not path or path.startswith("/") or ".." in Path(path).parts or ":" in path for path in paths):
            raise SelectInputError("变更路径必须是仓库相对路径")
        commands = load_commands(args.workflow)
        modes = load_modes(args.registry)
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
    unapproved = [
        (script, extra) for script, extra in commands
        if (script, tuple(extra)) not in modes
        or (modes[(script, tuple(extra))][0] not in RESTRICTED_CATEGORIES
            and not modes[(script, tuple(extra))][1])
    ]
    if unapproved or len({(script, tuple(extra)) for script, extra in commands}) != len(commands):
        print(f"[FAIL] SELECT-INPUT 命令清单有未登记/未批准的精确模式或重复项：{unapproved}")
        return INPUT_EXIT
    restricted = {identity for identity, (category, _ci) in modes.items()
                  if category in RESTRICTED_CATEGORIES}

    full = [(script, extra) for script, extra in commands
            if (script, tuple(extra)) not in restricted]
    if not full:
        print("[FAIL] SELECT-INPUT 完整离线集合为空（命令清单里全是受限模式）—— 不静默判绿。")
        return INPUT_EXIT

    try:
        wanted, reason = classify(paths, {script for script, _ in full}, {script for script, _ in modes})
    except SelectInputError as error:
        print(f"[FAIL] SELECT-INPUT {error}")
        return INPUT_EXIT
    if args.base and not paths:
        wanted, reason = DOCS, "已核对差量为空：仅必要管理检查"
    if wanted and any(script.startswith("tools/verify_v2") for script in wanted):
        wanted |= FRONTEND
    if "npm:test:domain" in wanted:
        wanted |= FRONTEND
    selected = full if not wanted else [item for item in full if item[0] in wanted]
    # 选择名在当前命令清单里找不到时，必须显式说出来（重命名/退出 CI 后不能静默少跑）。
    unresolved = sorted(wanted - {script for script, _ in full})
    if unresolved:
        print(("[FAIL] SELECT-INPUT 选择名不在当前命令清单里（可能已改名或退出 CI）："
               + "、".join(unresolved) + " —— 先同步分类表与真实命令，不静默少跑。")
              .encode("utf-8", "replace").decode("utf-8"))
        return INPUT_EXIT

    if not selected:
        print("[FAIL] SELECT-INPUT 没有适用命令，空集合不是通过")
        return INPUT_EXIT
    payload = {
        "reason": reason,
        "selected": [f"{script} {' '.join(extra)}".strip() for script, extra in selected],
        "full_count": len(full), "selected_count": len(selected),
        "unresolved": unresolved, "input_ok": True,
        "frontend": any(script.startswith("npm:") for script, _ in selected),
        "browser": any(script.startswith("tools/verify_v2") for script, _ in selected),
        "container": container_affected(paths) if args.base or paths else True,
    }
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
            for name in ("selected", "frontend", "browser", "container"):
                output.write(f"{name}={json.dumps(payload[name], ensure_ascii=False)}\n")
    if args.emit_github or args.github_output:
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    print(f"选择理由：{reason}".encode("utf-8", "replace").decode("utf-8"))
    print(f"完整离线集合 {len(full)} 条，本次选择 {len(selected)} 条"
          f"（受限 paid/remote/aggregate 模式 {len(restricted)} 条已排除）"
          .encode("utf-8", "replace").decode("utf-8"))
    if not args.run:
        return 0
    snapshot_before = snapshot_source() if args.result_json is not None else None
    started_at = utc_now() if args.result_json is not None else None
    executed: list[dict] = []
    for index, (script, extra) in enumerate(selected):
        argv_cmd = build_argv(script, extra)
        print(f"\n$ {' '.join(argv_cmd)}".encode("utf-8", "replace").decode("utf-8"))
        launched_at = utc_now() if args.result_json is not None else None
        try:
            proc = subprocess.run(argv_cmd, cwd=str(ROOT))
        except OSError as error:
            print(f"首个失败即停：{script} 启动失败（{type(error).__name__}: {error}），不继续后续命令")
            if args.result_json is not None:
                executed.append({"identity": f"{script} {' '.join(extra)}".strip(), "argv": argv_cmd,
                                 "started_at": launched_at, "finished_at": utc_now(), "status": "launch_failed",
                                 "returncode": None,
                                 "error": f"{type(error).__name__}: {error}"})
                remaining = [f"{item[0]} {' '.join(item[1])}".strip() for item in selected[index + 1:]]
                snapshot_after = snapshot_source()
                failure = write_result({
                    "schema": RESULT_SCHEMA, "status": "failed", "reason": reason,
                    "started_at": started_at, "finished_at": utc_now(),
                    "selection": payload["selected"], "executed": executed, "not_executed": remaining,
                    "first_failure_returncode": None, "input_ok": True, "notes": "命令启动失败：无进程退出码",
                    "source_before": snapshot_before, "source_after": snapshot_after,
                    "source_changed": snapshot_before != snapshot_after,
                })
                if failure is not None:
                    return failure
            return 1
        if args.result_json is not None:
            executed.append({"identity": f"{script} {' '.join(extra)}".strip(), "argv": argv_cmd,
                             "started_at": launched_at, "finished_at": utc_now(),
                             "status": "ok" if proc.returncode == 0 else "failed",
                             "returncode": proc.returncode})
        if proc.returncode != 0:
            print(f"首个失败即停：{script} 退出码 {proc.returncode}，不继续后续命令")
            if args.result_json is not None:
                remaining = [f"{item[0]} {' '.join(item[1])}".strip() for item in selected[index + 1:]]
                snapshot_after = snapshot_source()
                write_result({
                    "schema": RESULT_SCHEMA, "status": "failed", "reason": reason,
                    "started_at": started_at, "finished_at": utc_now(),
                    "selection": payload["selected"], "executed": executed, "not_executed": remaining,
                    "first_failure_returncode": proc.returncode, "input_ok": True,
                    "source_before": snapshot_before, "source_after": snapshot_after,
                    "source_changed": snapshot_before != snapshot_after,
                })
            return proc.returncode
    if args.result_json is not None:
        snapshot_after = snapshot_source()
        failure = write_result({
            "schema": RESULT_SCHEMA, "status": "passed", "reason": reason,
            "started_at": started_at, "finished_at": utc_now(),
            "selection": payload["selected"], "executed": executed, "not_executed": [],
            "first_failure_returncode": None, "input_ok": True,
            "source_before": snapshot_before, "source_after": snapshot_after,
            "source_changed": snapshot_before != snapshot_after,
        })
        if failure is not None:
            return failure
    print("所选命令全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
