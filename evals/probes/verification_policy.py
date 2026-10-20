#!/usr/bin/env python
"""真实分类 CLI 的独立配置反例；只写临时夹具，不修改 state/CI/登记权威。"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config/product-v2/verification.json"
WORKFLOW = ROOT / ".github/workflows/ci-cd.yml"
GUARD = ROOT / "tools/check_verification.py"
SELECTOR = ROOT / "tools/select_v2_checks.py"
TARGET = "tools/verify_v2_2_3_intake_understanding.py"
TAG = re.compile(r"^\[FAIL\] ([A-Z_]+)\b", re.M)
REGISTRY_SCHEMA = "amz-verification-registry/v1"

# 反例夹具只落在仓库内已忽略的 evals/.tmp/ 下：脚本要能相对 ROOT 被选择器执行。
FIXTURE_ROOT = ROOT / "evals" / ".tmp"


def selector_run(argv: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SELECTOR), *argv], cwd=ROOT,
                          text=True, capture_output=True, encoding="utf-8", timeout=timeout)


def selector_json(paths: list[str], *extra: str):
    """跑真实选择 CLI（--emit-github），返回 (进程, 解析后的选择结果|None)。"""
    result = selector_run([*paths, *extra, "--emit-github"])
    data = None
    if result.returncode == 0 and result.stdout.strip():
        try:
            data = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            data = None
    return result, data


def fixture_workflow(run_lines: list[str]) -> str:
    return yaml.safe_dump({"jobs": {"verify": {"steps": [
        {"name": "反例夹具命令", "run": "\n".join(run_lines) + "\n"}]}}}, allow_unicode=True, sort_keys=False)


def fixture_registry(modes: dict) -> str:
    return json.dumps({"schema": REGISTRY_SCHEMA, "entrypoints": modes,
                       "human_gates": {"C17": {"category": "manual"}, "C15": {"category": "manual"}}},
                      ensure_ascii=False)


def fixture_script(marker: Path, rc: int, tag: str) -> str:
    return ("import pathlib, sys\n"
            f"pathlib.Path(r'{marker.as_posix()}').write_text('ran', encoding='utf-8')\n"
            f"print('[OK  ] FIXTURE {tag}')\n"
            f"sys.exit({rc})\n")



def remove_ci(workflow: dict, entrypoint: str) -> None:
    changed = False
    for step in workflow["jobs"]["verify"]["steps"]:
        if "run" not in step:
            continue
        lines = step["run"].splitlines()
        kept = [line for line in lines if entrypoint not in line]
        if kept != lines:
            changed = True
            step["run"] = "\n".join(kept) + "\n"
    if not changed:
        raise RuntimeError(f"反例未改动 CI：{entrypoint}")


def add_ci(workflow: dict, command: str, identity: str) -> None:
    workflow["jobs"]["verify"]["steps"].append({
        "name": "独立反例", "run": command,
        "if": f"contains(fromJSON(needs.changes.outputs.selected), '{identity}')",
    })


def main() -> int:
    original = {path: path.read_bytes() for path in (REGISTRY, WORKFLOW, ROOT / "package.json")}
    baseline = json.loads(original[REGISTRY])
    workflow = yaml.safe_load(original[WORKFLOW])
    cases = []

    def case(code: str, mutate, tags: set[str]) -> None:
        registry_copy = copy.deepcopy(baseline)
        workflow_copy = copy.deepcopy(workflow)
        mutate(registry_copy, workflow_copy)
        if tags and registry_copy == baseline and workflow_copy == workflow:
            raise RuntimeError(f"{code} 没有真正注入漂移")
        cases.append((code, registry_copy, workflow_copy, tags))

    case("VPC01", lambda _r, _w: None, set())
    case("VPC02", lambda r, _w: r["entrypoints"].pop(TARGET),
         {"VCLASS_MISSING", "CI_UNCLASSIFIED"})
    case("VPC03", lambda _r, w: remove_ci(w, TARGET), {"CI_MISSING"})
    case("VPC04", lambda _r, w: remove_ci(w, "npm run check:types"), {"CI_MISSING"})
    case("VPC05", lambda _r, w: remove_ci(w, "npm run test:domain"), {"CI_MISSING"})
    live = "tools/verify_v2_2_2_semantic_provider.py"
    case("VPC06", lambda _r, w: add_ci(w, f"uv run python {live} --live", f"{live} --live"), {"CI_UNCLASSIFIED"})

    def enable_paid(registry, wf):
        registry["entrypoints"][live][1]["ci"] = True
        add_ci(wf, f"uv run python {live} --live", f"{live} --live")

    case("VPC07", enable_paid, {"CI_RESTRICTED", "CI_UNCLASSIFIED"})

    def enable_restricted(entrypoint: str):
        def mutate(registry, wf):
            registry["entrypoints"][entrypoint][0]["ci"] = True
            add_ci(wf, f"uv run python {entrypoint}", entrypoint)
        return mutate

    case("VPC08", enable_restricted("tools/verify_v2_ui_1_remote_entry.py"),
         {"CI_RESTRICTED", "CI_UNCLASSIFIED"})
    case("VPC09", enable_restricted("tools/verify_v2_7_1_regression.py"),
         {"CI_RESTRICTED", "CI_UNCLASSIFIED"})
    case("VPC10", lambda r, _w: r["human_gates"]["C17"].update(category="browser"), {"VCLASS_HUMAN"})
    case("VPC11", lambda r, _w: r["human_gates"].pop("C15"), {"VCLASS_HUMAN"})
    case("VPC12", lambda _r, w: add_ci(w, f"uv run python {TARGET}", TARGET), {"CI_DUPLICATE"})
    case("VPC13", lambda r, _w: r["entrypoints"][TARGET][0].update(category="unknown"),
         {"VCLASS_SCHEMA", "CI_UNCLASSIFIED"})
    case("VPC14", lambda r, _w: r["entrypoints"].update({"tools/verify_v2_ghost.py": [
        {"args": [], "category": "browser", "ci": False, "reason": "仅临时幽灵登记反例"}]}),
         {"VCLASS_GHOST"})
    # ---- T5 选择器：只验真实选择/执行/跳过的后果，不做源文本自匹配绿灯 ----
    failed = 0
    t5_count = 0

    def judge(code: str, condition: bool, detail: str) -> None:
        nonlocal failed, t5_count
        t5_count += 1
        print(f"[{'OK  ' if condition else 'FAIL'}] {code} {detail}")
        if not condition:
            failed += 1

    base_result, base = selector_json([])
    judge("T5-FULL-BASELINE", base_result.returncode == 0 and bool(base),
          f"rc={base_result.returncode} full={base and base['full_count']}")
    full_selection = set(base["selected"]) if base else set()
    if not base:
        print(base_result.stdout)
        print(base_result.stderr)

    # 1) 普通说明：只选控制面，不启动浏览器消费者
    docs_result, docs = selector_json(["docs/drafts/requirements-analysis-2026-09-24.md"])
    judge("T5-DOC-PROSE",
          docs_result.returncode == 0 and bool(docs) and 0 < docs["selected_count"] < docs["full_count"]
          and not any("verify_v2" in item for item in docs["selected"]),
          f"rc={docs_result.returncode} selected={docs and docs['selected_count']}/"
          f"{docs and docs['full_count']}")

    # 公共读写/出站合同、锁与未知影响仍保守扩大；不是所有业务/策略变化都必须全选。
    for path in ("app/product_v2/session.ts", "app/server.py", "src/providers/v2_image.py",
                 "uv.lock", "package.json", "some/random/path.xyz"):
        result, data = selector_json([path])
        judge("T5-FULL-" + path.replace("/", "_").replace(".", "-"),
              result.returncode == 0 and bool(data) and set(data["selected"]) == full_selection,
              f"rc={result.returncode} selected={data and data['selected_count']}/{data and data['full_count']}")
    proof_path = "_stage-amz-control/b18-optional-figures-20261020/closeout-stop-20261020.md"
    proof_result, proof = selector_json([proof_path])
    judge("T5-PROOF-ONLY",
          proof_result.returncode == 0 and bool(proof)
          and proof["selected"] == ["tools/check_docs.py --no-run"]
          and not proof["container"] and not proof["browser"],
          f"rc={proof_result.returncode} selected={proof and proof['selected']}")
    ui_path = "app/product_v2/ui/generation-view.ts"
    ui_result, ui = selector_json([ui_path])
    # generation-view 独占 #task-list-mount / #shot-execution：凡真实读取这两个根的工具都在
    # 同一条依赖上。要求集从源码派生，避免手写名单再次静默漏掉新的验证器。
    paid_readers = {"tools/verify_v2_4_5_live_reference.py"}  # 付费/直连，离线集合不选它
    generation_readers = {
        "tools/" + path.name
        for path in (ROOT / "tools").glob("verify_v2*.py")
        if any(sel in path.read_text(encoding="utf-8")
               for sel in ("#task-list-mount", "#shot-execution"))
    } - paid_readers
    ui_required = ({"npm:check:types", "npm:build:frontend"}
                   | generation_readers
                   | {"tools/verify_v2_ui_2_interaction_visual.py",
                      "tools/verify_v2_ui_3_frontend.py",
                      "tools/verify_v2_6_4_accessibility.py"})
    judge("T5-GENERATION-CONSUMERS",
          ui_result.returncode == 0 and bool(ui) and ui_required <= set(ui["selected"])
          and "tools/verify_v2_1_3_project_package.py" not in ui["selected"]
          and ui["container"] and ui["browser"] and ui["frontend"],
          f"rc={ui_result.returncode} selected={ui and ui['selected_count']} "
          f"required={len(ui_required)} missing={sorted(ui_required - set(ui['selected'])) if ui else '?'}")
    verifier_result, verifier = selector_json(["tools/verify_v2_4_4_candidate_blob.py"])
    judge("T5-VERIFIER-OWN-CONSUMER",
          verifier_result.returncode == 0 and bool(verifier)
          and "tools/verify_v2_4_4_candidate_blob.py" in verifier["selected"]
          and "tools/verify_v2_1_3_project_package.py" not in verifier["selected"]
          and verifier["browser"] and not verifier["container"],
          f"rc={verifier_result.returncode} selected={verifier and verifier['selected_count']}")
    mixed_result, mixed = selector_json([proof_path, ui_path])
    judge("T5-MIXED-UNION",
          mixed_result.returncode == 0 and bool(mixed) and bool(ui) and bool(proof)
          and set(mixed["selected"]) == set(proof["selected"]) | set(ui["selected"]),
          f"rc={mixed_result.returncode} selected={mixed and mixed['selected_count']}")
    rehearsal_result, _ = selector_json(["tools/rehearse_v273_walkthrough.py"])
    judge("T5-REHEARSAL-NEEDS-INPUT",
          rehearsal_result.returncode == 2 and "SELECT-INPUT" in rehearsal_result.stdout,
          f"rc={rehearsal_result.returncode} 缺素材/批准模式不冒充走查已验")
    plan_result, plan = selector_json(["docs/product-v2-refactor-plan.md"])
    judge("T5-PLAN-STATE-CONSISTENCY",
          plan_result.returncode == 0 and bool(plan)
          and "evals/probes/project_state.py" in plan["selected"]
          and "tools/check_project_state.py" in plan["selected"] and not plan["container"],
          f"rc={plan_result.returncode} selected={plan and plan['selected']}")
    for path in ("tools/verify_v2_7_1_regression.py", "tools/verify_v2_removed_fixture.py"):
        result, data = selector_json([path])
        judge("T5-VERIFIER-MAINTENANCE-" + Path(path).stem,
              result.returncode == 0 and bool(data)
              and set(data["selected"]) == {"tools/check_verification.py", "evals/probes/verification_policy.py"}
              and path not in data["selected"] and not data["container"],
              f"rc={result.returncode} maintenance_only={data and data['selected']}")
    for path, expected_container in (
        ("config/product-v2/verification.json", False),
        ("tools/select_v2_checks.py", False),
        (".github/workflows/ci-cd.yml", True),
        ("tools/export_image_envelope_schema.py", True),
        ("tools/generate_image_envelope_validator.mjs", True),
        (".dockerignore", True),
        ("config/product-v2/providers.json", True),
        ("deploy/release-transaction.sh", True),
        ("tools/release_transaction_probe.py", True),
    ):
        result, data = selector_json([path])
        judge("T5-RELEASE-IMPACT-" + path.replace("/", "_"),
              result.returncode == 0 and bool(data) and data["container"] is expected_container,
              f"rc={result.returncode} container={data and data['container']}")
    invalid_base, _ = selector_json([], "--base", "0" * 40, "--head", "f" * 40)
    judge("T5-BAD-GIT-BASE",
          invalid_base.returncode == 2 and "SELECT-INPUT" in invalid_base.stdout,
          f"rc={invalid_base.returncode} 坏差量不能按证据-only跳过")
    # 受限模式不得被普通批次选中
    judge("T5-RESTRICTED-EXCLUDED",
          bool(base) and not any("--live" in item for item in base["selected"]),
          f"restricted_in_full={base and [i for i in base['selected'] if '--live' in i]}")

    # 3) 分类依赖 fail-closed：登记坏、命令清单坏 → 明确失败且一条命令都不执行
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="v2-select-fixture-", dir=str(FIXTURE_ROOT)))
    try:
        def rel(path: Path) -> str:
            return path.relative_to(ROOT).as_posix()

        marker_ok = workdir / "ran-ok.marker"
        marker_paid = workdir / "ran-paid.marker"
        marker_first = workdir / "ran-first.marker"
        marker_second = workdir / "ran-second.marker"
        script_ok = workdir / "fixture_ok.py"
        script_paid = workdir / "fixture_paid.py"
        script_first = workdir / "fixture_first.py"
        script_second = workdir / "fixture_second.py"
        script_ok.write_text(fixture_script(marker_ok, 0, "OK"), encoding="utf-8")
        script_paid.write_text(fixture_script(marker_paid, 0, "PAID"), encoding="utf-8")
        script_first.write_text(fixture_script(marker_first, 3, "FIRST"), encoding="utf-8")
        script_second.write_text(fixture_script(marker_second, 0, "SECOND"), encoding="utf-8")

        ok_entry, paid_entry = rel(script_ok), rel(script_paid)
        ok_line = f"uv run --locked python {ok_entry}\n"
        paid_line = f"uv run --locked python {paid_entry} --live\n"
        valid_registry = fixture_registry({
            ok_entry: [{"args": [], "category": "browser", "ci": True}],
            paid_entry: [{"args": ["--live"], "category": "paid", "ci": False, "reason": "反例：真实计费模式"}],
        })
        bad_schema_text = fixture_registry({
            ok_entry: [{"args": [], "category": "browser", "ci": True}]}).replace(REGISTRY_SCHEMA, "amz-registry/other")
        bad_category_text = fixture_registry({
            ok_entry: [{"args": [], "category": "unknown", "ci": True}]})

        def fixture_files(name: str, workflow_text: str, registry_text: str):
            wf = workdir / f"{name}.workflow.yml"
            reg = workdir / f"{name}.registry.json"
            wf.write_text(workflow_text, encoding="utf-8")
            reg.write_text(registry_text, encoding="utf-8")
            return rel(wf), rel(reg)

        okay_workflow = fixture_workflow([ok_line.rstrip("\n")])
        wf_ok, reg_ok = fixture_files("run", okay_workflow, valid_registry)
        # 同一条（会真执行并写 marker 的）夹具命令配坏登记：这样才能证明「没执行」是登记校验拦下的，
        # 而不是夹具本身跑不动。工作流故意复用 wf_ok 的字节。
        wf_bad_schema, reg_bad_schema = fixture_files("badreg", okay_workflow, bad_schema_text)
        wf_bad_category, reg_bad_category = fixture_files("badcat", okay_workflow, bad_category_text)
        wf_paid, reg_paid = fixture_files("paid", fixture_workflow([paid_line.rstrip("\n"), ok_line.rstrip("\n")]),
                                          valid_registry)
        wf_unparsed, _ = fixture_files(
            "unparsed", fixture_workflow(["uv run --locked pytest tools/fixture_gateway_group.py"]), valid_registry)
        wf_first_fail, reg_first = fixture_files(
            "firstfail", fixture_workflow([f"uv run --locked python {rel(script_first)}",
                                           f"uv run --locked python {rel(script_second)}"]),
            fixture_registry({rel(script_first): [{"args": [], "category": "browser", "ci": True}],
                              rel(script_second): [{"args": [], "category": "browser", "ci": True}]}))

        def run_with(args: list[str]):
            return selector_run([*args, "--run"])

        def marker_state() -> dict:
            return {p.name: p.exists() for p in (marker_ok, marker_paid, marker_first, marker_second)}

        before = marker_state()
        # (a) 登记 schema 不对：必须明确失败，且不得执行任何命令
        bad = run_with(["some/unknown/path.xyz", "--workflow", wf_bad_schema, "--registry", reg_bad_schema])
        judge("T5-BAD-REGISTRY-SCHEMA",
              bad.returncode == 2 and "SELECT-INPUT" in bad.stdout and marker_state() == before,
              f"rc={bad.returncode} markers={marker_state()}")
        # (b) 分类取值非法：同上
        bad_cat = run_with(["some/unknown/path.xyz", "--workflow", wf_bad_category, "--registry", reg_bad_category])
        judge("T5-BAD-REGISTRY-CATEGORY",
              bad_cat.returncode == 2 and "SELECT-INPUT" in bad_cat.stdout and marker_state() == before,
              f"rc={bad_cat.returncode} markers={marker_state()}")
        # (c) 命令清单里出现解析器还不认识的验证命令：明确失败，不静默少跑
        unparsed = run_with(["some/unknown/path.xyz", "--workflow", wf_unparsed, "--registry", reg_ok])
        judge("T5-UNPARSED-COMMAND",
              unparsed.returncode == 2 and "SELECT-INPUT" in unparsed.stdout and marker_state() == before,
              f"rc={unparsed.returncode}")
        # 同一条可执行夹具，实际模式未变而选择条件拼错：必须拒绝，不能被skip洗成绿。
        wrong_route = yaml.safe_load(okay_workflow)
        wrong_route["jobs"]["changes"] = {"outputs": {"selected": "fixture"}}
        wrong_route["jobs"]["verify"]["steps"][0]["if"] = "contains(fromJSON(needs.changes.outputs.selected), 'wrong-mode')"
        wf_route, reg_route = fixture_files(
            "badroute", yaml.safe_dump(wrong_route), valid_registry)
        route_rejected = run_with(["some/unknown/path.xyz", "--workflow", wf_route, "--registry", reg_route])
        judge("T5-ROUTING-REFUSES-SILENT-SKIP",
              route_rejected.returncode == 2 and "CI_ROUTING" in route_rejected.stdout
              and marker_state() == before,
              f"rc={route_rejected.returncode} markers={marker_state()}")
        # (d) 正常夹具真跑：确认夹具本身有效（否则后面几条会假绿）
        good = run_with(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok])
        judge("T5-FIXTURE-EXECUTES",
              good.returncode == 0 and marker_ok.exists(),
              f"rc={good.returncode} marker_ok={marker_ok.exists()}")
        # (e) 首个失败保留真实退出码，后续命令不执行
        first_fail = run_with(["some/unknown/path.xyz", "--workflow", wf_first_fail, "--registry", reg_first])
        judge("T5-FIRST-FAIL-STOPS",
              first_fail.returncode == 3 and marker_first.exists() and not marker_second.exists(),
              f"rc={first_fail.returncode} first={marker_first.exists()} second={marker_second.exists()}")
        # (f) 受限（paid）模式不进选择结果，也不会被执行
        paid_result, paid_data = selector_json(["some/unknown/path.xyz", "--workflow", wf_paid, "--registry", reg_paid])
        judge("T5-PAID-MODE-EXCLUDED",
              paid_result.returncode == 0 and bool(paid_data)
              and paid_data["selected"] == [ok_entry] and paid_data["selected_count"] == 1,
              f"rc={paid_result.returncode} selected={paid_data and paid_data['selected']}")
        paid_run = run_with(["some/unknown/path.xyz", "--workflow", wf_paid, "--registry", reg_paid])
        judge("T5-PAID-NOT-EXECUTED",
              paid_run.returncode == 0 and marker_ok.exists() and not marker_paid.exists(),
              f"rc={paid_run.returncode} ok={marker_ok.exists()} paid={marker_paid.exists()}")
        # 精确模式准入：复用既有本地试验的独立 marker；坏项在后也不能先执行好项。
        for name in ("unknown-entry", "unknown-args", "not-approved", "duplicate-mode",
                     "restricted-approved", "invalid-ci", "mixed-plan", "duplicate-plan"):
            marker = workdir / f"{name}.marker"
            prefix_marker = workdir / f"{name}-prefix.marker"
            script = workdir / f"{name}.py"
            script.write_text(fixture_script(marker, 0, name), encoding="utf-8")
            entry = rel(script)
            approved = {"args": [], "category": "control", "ci": True}
            modes = [approved]
            command = f"uv run --locked python {entry}"
            entries = {ok_entry: [{"args": [], "category": "control", "ci": True}]}
            lines = [command]
            if name == "unknown-entry":
                modes = None
            elif name == "unknown-args":
                lines = [command + " --live"]
            elif name == "not-approved":
                modes = [{"args": [], "category": "control", "ci": False,
                          "reason": "独立反例：未批准执行"}]
            elif name == "duplicate-mode":
                modes = [approved, {"args": [], "category": "paid", "ci": False,
                                    "reason": "独立反例：同一模式分类冲突"}]
            elif name == "restricted-approved":
                modes = [{"args": [], "category": "paid", "ci": True}]
            elif name == "invalid-ci":
                modes = [{"args": [], "category": "control", "ci": "true"}]
            elif name == "mixed-plan":
                modes = None
                prefix_script = workdir / f"{name}-prefix.py"
                prefix_script.write_text(fixture_script(prefix_marker, 0, "PREFIX"), encoding="utf-8")
                prefix_entry = rel(prefix_script)
                entries[prefix_entry] = [approved]
                lines.insert(0, f"uv run --locked python {prefix_entry}")
            elif name == "duplicate-plan":
                lines.append(command)
            if modes is not None:
                entries[entry] = modes
            wf, reg = fixture_files(name, fixture_workflow(lines), fixture_registry(entries))
            before_markers = marker_state()
            rejected = run_with(["some/unknown/path.xyz", "--workflow", wf, "--registry", reg])
            judge("T5-EXACT-" + name.upper(),
                  rejected.returncode == 2 and "SELECT-INPUT" in rejected.stdout
                  and not marker.exists() and not prefix_marker.exists()
                  and marker_state() == before_markers,
                  f"rc={rejected.returncode} unapproved_executed={marker.exists()}")
        output_path = workdir / "github-output.txt"
        output_result, output_data = selector_json(
            [proof_path], "--github-output", str(output_path))
        outputs = dict(line.split("=", 1) for line in output_path.read_text(encoding="utf-8").splitlines())
        judge("T5-GITHUB-OUTPUT",
              output_result.returncode == 0 and bool(output_data)
              and json.loads(outputs["selected"]) == ["tools/check_docs.py --no-run"]
              and json.loads(outputs["container"]) is False
              and json.loads(outputs["browser"]) is False,
              f"rc={output_result.returncode} container={outputs.get('container')}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


    with tempfile.TemporaryDirectory(prefix="amz-verification-policy-") as temporary:
        fixture_root = Path(temporary)
        registry_path = fixture_root / "verification.json"
        workflow_path = fixture_root / "workflow.yml"
        for code, registry, wf, expected in cases:
            registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
            workflow_path.write_text(yaml.safe_dump(wf, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(GUARD), "--registry", str(registry_path),
                                     "--workflow", str(workflow_path)], cwd=ROOT,
                                    text=True, capture_output=True, encoding="utf-8", timeout=30)
            tags = set(TAG.findall(result.stdout))
            wanted_rc = 1 if expected else 0
            ok = result.returncode == wanted_rc and tags == expected
            print(f"[{'OK' if ok else 'FAIL'}] {code} rc={result.returncode} tags={sorted(tags)}")
            if not ok:
                failed += 1
                print(result.stdout)
                print(result.stderr)
    changed = [str(path.relative_to(ROOT)) for path, data in original.items()
               if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(data).digest()]
    if changed:
        failed += 1
        print(f"[FAIL] AUTHORITY_MUTATION {changed}")
    if failed:
        return 1
    print(f"[PASS] VERIFICATION-PROBES {len(cases)} 组 + T5 选择/执行后果 {t5_count} 项；"
          f"真实 CLI 拒绝遗漏/受限接线，未修改权威文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
