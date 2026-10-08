#!/usr/bin/env python
"""R3.2 验证分类门：CI 持有命令，登记只持有分类/权限；遗漏和付费接线均判红。"""
from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci-cd.yml"
REGISTRY = ROOT / "config/product-v2/verification.json"
CATEGORIES = {"control", "types", "domain", "browser", "gateway", "paid", "remote", "aggregate"}
RESTRICTED = {"paid", "remote", "aggregate"}


def ci_commands(workflow: Path = WORKFLOW) -> list[tuple[str, list[str]]]:
    """只读 verify job；命令权威仍是工作流，不在登记复制可执行清单。"""
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    steps = document["jobs"]["verify"]["steps"]
    commands = []
    for step in steps:
        for line in str(step.get("run", "")).splitlines():
            tokens = shlex.split(line.strip(), comments=True)
            if tokens[:2] == ["uv", "run"]:
                rest = tokens[2:]
                if rest[:1] == ["--locked"]:
                    rest = rest[1:]
                if len(rest) >= 2 and rest[0] == "python" and rest[1].endswith(".py"):
                    commands.append((rest[1], rest[2:]))
            elif len(tokens) >= 3 and tokens[:2] == ["npm", "run"]:
                args = tokens[3:]
                if args[:1] == ["--"]:
                    args = args[1:]
                commands.append(("npm:" + tokens[2], args))
    return commands


def check_policy(registry: dict, commands: list[tuple[str, list[str]]], root: Path = ROOT
                 ) -> list[tuple[str, str]]:
    problems = []
    if not isinstance(registry, dict) or registry.get("schema") != "amz-verification-registry/v1":
        return [("VCLASS_SCHEMA", "验证分类 schema 不受支持")]
    entries = registry.get("entrypoints")
    if not isinstance(entries, dict):
        return [("VCLASS_SCHEMA", "entrypoints 必须是对象")]
    manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
    scripts = manifest.get("scripts", {})
    inventory = {path.relative_to(root).as_posix() for path in (root / "tools").glob("verify_v2*.py")}
    inventory.update("npm:" + name for name in scripts)
    missing = inventory - entries.keys()
    if missing:
        problems.append(("VCLASS_MISSING", "未分类入口：" + ", ".join(sorted(missing))))
    allowed = set()
    required = set()
    for entrypoint, modes in entries.items():
        exists = entrypoint[4:] in scripts if entrypoint.startswith("npm:") else (root / entrypoint).is_file()
        if not exists:
            problems.append(("VCLASS_GHOST", f"登记入口不存在：{entrypoint}"))
        if not isinstance(modes, list) or not modes:
            problems.append(("VCLASS_SCHEMA", f"入口必须有模式：{entrypoint}"))
            continue
        seen = set()
        for mode in modes:
            if not isinstance(mode, dict):
                problems.append(("VCLASS_SCHEMA", f"模式必须是对象：{entrypoint}"))
                continue
            args = mode.get("args")
            category = mode.get("category")
            ci = mode.get("ci")
            if (not isinstance(args, list) or any(not isinstance(arg, str) for arg in args)
                    or category not in CATEGORIES or not isinstance(ci, bool)):
                problems.append(("VCLASS_SCHEMA", f"模式字段不合法：{entrypoint}"))
                continue
            identity = (entrypoint, tuple(args))
            if identity in seen:
                problems.append(("VCLASS_DUPLICATE", f"重复模式：{identity}"))
            seen.add(identity)
            if not ci and not mode.get("reason"):
                problems.append(("VCLASS_SCHEMA", f"排除 CI 必须说明权限/覆盖理由：{identity}"))
            if ci and category in RESTRICTED:
                problems.append(("CI_RESTRICTED", f"受限入口不得进入 CI：{identity}"))
            elif ci:
                allowed.add(identity)
                required.add(identity)
    actual = [(entrypoint, tuple(args)) for entrypoint, args in commands]
    if len(set(actual)) != len(actual):
        problems.append(("CI_DUPLICATE", "CI 重复执行同一验证模式"))
    for identity in sorted(required - set(actual)):
        problems.append(("CI_MISSING", f"CI 缺少已登记必跑模式：{identity}"))
    for identity in sorted(set(actual) - allowed):
        problems.append(("CI_UNCLASSIFIED", f"CI 执行未批准/受限模式：{identity}"))
    gates = registry.get("human_gates")
    if not isinstance(gates, dict) or set(gates) != {"C17", "C15"}:
        problems.append(("VCLASS_HUMAN", "C17/C15 必须明确分类为人工门，不以自动套件替代"))
    elif any(gate != {"category": "manual"} for gate in gates.values()):
        problems.append(("VCLASS_HUMAN", "人工门不得登记为自动验证"))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY, help="反向探针的独立登记夹具")
    parser.add_argument("--workflow", type=Path, default=WORKFLOW, help="反向探针的独立 CI 夹具")
    args = parser.parse_args()
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        commands = ci_commands(args.workflow)
        problems = check_policy(registry, commands)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"[FAIL] VCLASS_INPUT {error}")
        return 1
    for code, detail in problems:
        print(f"[FAIL] {code} {detail}")
    if problems:
        return 1
    print(f"[PASS] VERIFICATION-POLICY {len(registry['entrypoints'])} 入口 / {len(commands)} CI 模式；付费、远程、人审独立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
