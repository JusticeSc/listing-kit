"""为当前 v2 生成可重建、可定位的基线证据。

它不把样例图“采纳”为业务交付，也不声称生成背景能逐像素复现；它冻结的是：
同一输入与配置对应哪次 run、当时的代码/依赖身份、实际产物哈希和回归结论。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
from datetime import datetime
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

DEFAULT_MANIFEST = ROOT / "evals" / "v2_baseline_manifest.json"
DEFAULT_REPORT = ROOT / "evals" / "v2_baseline_snapshot.txt"
SOURCE_ROOTS = ("config", "src", "tools", "web")
SOURCE_FILES = ("run.py", "requirements.txt", "requirements-rembg.txt")
PACKAGES = ("pillow", "numpy", "requests", "PyYAML", "python-dotenv", "rembg", "onnxruntime")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_row(path: Path, base: Path) -> dict:
    return {
        "path": path.relative_to(base).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def latest_run() -> Path:
    runs = sorted(p for p in (ROOT / "out").glob("*") if (p / "plan.json").is_file())
    if not runs:
        raise RuntimeError("out/ 下没有含 plan.json 的 run；先执行一次 --fresh 回归")
    return runs[-1]


def resolve_run(raw: str | None) -> Path:
    path = Path(raw) if raw else latest_run()
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    out = (ROOT / "out").resolve()
    if path.parent != out or not (path / "plan.json").is_file() or not (path / "run.jsonl").is_file():
        raise RuntimeError(f"不是 out/ 下完整的 run：{path}")
    return path


def source_files() -> list[Path]:
    files: list[Path] = []
    for rel in SOURCE_FILES:
        path = ROOT / rel
        if path.is_file():
            files.append(path)
    for rel in SOURCE_ROOTS:
        base = ROOT / rel
        files.extend(p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    # evals/ 里既有判据源码也有本工具生成的 manifest/report；只纳入 Python 判据，
    # 避免把输出文件哈希进自己的版本身份形成循环。
    files.extend(p for p in (ROOT / "evals").rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(set(files), key=lambda p: p.relative_to(ROOT).as_posix())


def tree_identity(files: list[Path]) -> tuple[str, list[dict]]:
    rows = [file_row(path, ROOT) for path in files]
    h = hashlib.sha256()
    for row in rows:
        h.update(row["path"].encode("utf-8"))
        h.update(b"\0")
        h.update(row["sha256"].encode("ascii"))
        h.update(b"\n")
    return h.hexdigest(), rows


def package_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in PACKAGES:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = "not-installed"
    return result


def existing_input_rows(plan: dict) -> list[dict]:
    paths: list[Path] = []
    product = Path(str(plan.get("product") or ""))
    if product.is_file():
        paths.append(product)
    for value in (plan.get("supplied") or {}).values():
        path = Path(str(value))
        if path.is_file():
            paths.append(path)
    return [file_row(path.resolve(), ROOT) for path in sorted(set(paths))]


def report_result(report: Path) -> str:
    if not report.is_file():
        return "missing"
    for line in reversed(report.read_text(encoding="utf-8").splitlines()):
        if line.startswith("结论："):
            return line
    return "result-line-missing"


def build(run_dir: Path) -> dict:
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    code_hash, code_files = tree_identity(source_files())
    regress = ROOT / "evals" / "last_regress.txt"
    artifacts = [file_row(path, run_dir) for path in sorted(run_dir.rglob("*")) if path.is_file()]
    return {
        "schema": "amz-listing-kit/v2-baseline@1",
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "claim_boundary": {
            "proves": "该 v2 代码/依赖/输入在本机产生了此 run，且当前完整回归结果可定位",
            "does_not_prove": "不证明真实 SKU 事实正确、运营采纳、生产可用性或生成背景逐像素复现",
        },
        "run": {
            "id": run_dir.name,
            "path": str(run_dir),
            "upc": plan.get("upc"),
            "slot_ids": [slot.get("slot_id") for slot in plan.get("slots") or []],
            "renderers": {str(slot.get("slot_id")): slot.get("renderer") for slot in plan.get("slots") or []},
            "skipped": plan.get("skipped") or [],
            "declared_model_calls": plan.get("model_calls"),
            "plan": "plan.json",
            "event_log": "run.jsonl",
        },
        "inputs": existing_input_rows(plan),
        "artifacts": artifacts,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": package_versions(),
        },
        "version_identity": {
            "kind": "content-tree-sha256",
            "sha256": code_hash,
            "source_file_count": len(code_files),
            "source_files": code_files,
            "note": "项目不是 Git 仓库，因此以相对路径+文件 SHA-256 的聚合指纹代替 commit id",
        },
        "regression": {
            "path": str(regress),
            "sha256": sha256(regress) if regress.is_file() else None,
            "result": report_result(regress),
        },
        "known_limits": [
            "这是满素材样例的工程基线，不是 20 个真实 SKU 的产品验收",
            "位置 4 调用生成模型，重跑应复现合同与门禁，不承诺背景像素相同",
            "plan.json 记录系统字体来源为自动探测，商用授权仍未确认",
            "正式 Product V1 的数据授权、预算硬门、幂等与 Unknown 核对尚未进入本阶段",
        ],
        "reproduce": [
            "$PY tools/regress_all.py --fresh",
            f"$PY tools/snapshot_v2_baseline.py --run out/{run_dir.name}",
        ],
    }


def render_text(manifest: dict, manifest_path: Path) -> str:
    run = manifest["run"]
    version = manifest["version_identity"]
    regression = manifest["regression"]
    lines = [
        "v2 基线快照",
        "=" * 72,
        f"时间：{manifest['captured_at']}",
        f"Run：{run['id']}",
        f"Run 目录：{run['path']}",
        f"输入：{len(manifest['inputs'])} 个文件（逐文件 SHA-256 见 manifest）",
        f"产物：{len(manifest['artifacts'])} 个文件（含 plan.json / run.jsonl / raw / 各版本）",
        f"槽位：{run['slot_ids']}；跳过：{run['skipped'] or '无'}；计划模型调用：{run['declared_model_calls']}",
        f"代码身份：content-tree-sha256 {version['sha256']}（{version['source_file_count']} 个文件）",
        f"回归：{regression['result']}",
        f"Manifest：{manifest_path}",
        "",
        "重现：",
        *[f"  {cmd}" for cmd in manifest["reproduce"]],
        f"  $PY tools/snapshot_v2_baseline.py --check --manifest {manifest_path.relative_to(ROOT).as_posix()}",
        "",
        "边界：",
        f"  能证明：{manifest['claim_boundary']['proves']}",
        f"  不能证明：{manifest['claim_boundary']['does_not_prove']}",
        "",
        "已知限制：",
        *[f"  - {item}" for item in manifest["known_limits"]],
        "",
    ]
    return "\n".join(lines)


def check_manifest(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    run_dir = Path(str((data.get("run") or {}).get("path") or ""))
    if not run_dir.is_dir() or run_dir.name != (data.get("run") or {}).get("id"):
        problems.append(f"run 不存在或 id 不匹配：{run_dir}")

    for section, base in (("inputs", ROOT), ("artifacts", run_dir)):
        for row in data.get(section) or []:
            item = base / str(row.get("path") or "")
            if not item.is_file():
                problems.append(f"{section} 文件不存在：{item}")
            elif item.stat().st_size != row.get("size_bytes") or sha256(item) != row.get("sha256"):
                problems.append(f"{section} 哈希或大小已变化：{item}")

    # 逐行验哈希只能发现“登记过的东西变了”，发现不了目录里偷偷多出文件。
    # 冻结基线的产物集合必须是精确集合，不能靠重打快照把漂移吞掉。
    if run_dir.is_dir():
        expected = [str(row.get("path") or "") for row in data.get("artifacts") or []]
        duplicates = sorted({path for path in expected if expected.count(path) > 1})
        if duplicates:
            problems.append("artifacts 存在重复登记：" + "、".join(duplicates))
        expected_set = set(expected)
        actual_set = {item.relative_to(run_dir).as_posix()
                      for item in run_dir.rglob("*") if item.is_file()}
        extras = sorted(actual_set - expected_set)
        missing = sorted(expected_set - actual_set)
        if extras:
            problems.append("artifacts 出现未登记文件：" + "、".join(extras))
        if missing:
            problems.append("artifacts 集合缺少已登记文件：" + "、".join(missing))

    current_hash, current_rows = tree_identity(source_files())
    version = data.get("version_identity") or {}
    if current_hash != version.get("sha256") or len(current_rows) != version.get("source_file_count"):
        problems.append("代码树身份已变化：请在新的完整回归通过后重新生成基线")

    regression = data.get("regression") or {}
    regress_path = Path(str(regression.get("path") or ""))
    if not regress_path.is_file() or sha256(regress_path) != regression.get("sha256"):
        problems.append("完整回归报告缺失或哈希已变化")
    return problems


def self_test() -> int:
    """反向探针：多一个文件时，必须由集合守卫明确报红。"""
    tmp_parent = ROOT / "evals" / ".tmp"
    tmp_parent.mkdir(parents=True, exist_ok=True)
    current_hash, current_rows = tree_identity(source_files())
    regress = ROOT / "evals" / "last_regress.txt"
    with tempfile.TemporaryDirectory(prefix="baseline-extra-file-", dir=tmp_parent) as raw:
        base = Path(raw)
        run_dir = base / "probe-run"
        run_dir.mkdir()
        keep = run_dir / "keep.txt"
        keep.write_text("registered\n", encoding="utf-8")
        data = {
            "run": {"id": run_dir.name, "path": str(run_dir)},
            "inputs": [],
            "artifacts": [file_row(keep, run_dir)],
            "version_identity": {"sha256": current_hash,
                                   "source_file_count": len(current_rows)},
            "regression": {"path": str(regress),
                           "sha256": sha256(regress) if regress.is_file() else None},
        }
        manifest = base / "manifest.json"
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        (run_dir / "extra.txt").write_text("must be detected\n", encoding="utf-8")
        problems = check_manifest(manifest)
    expected = [problem for problem in problems
                if problem.startswith("artifacts 出现未登记文件：")
                and "extra.txt" in problem]
    unrelated = [problem for problem in problems if problem not in expected]
    if len(expected) != 1 or unrelated:
        print("未通过：额外文件反向探针没有得到唯一、明确的集合漂移结论")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1
    print("OK：故意增加 extra.txt 时，baseline 集合守卫明确变红")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", help="out/ 下的 run 目录；默认取最新完整 run")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--report", default=str(DEFAULT_REPORT))
    ap.add_argument("--check", action="store_true", help="只读复核既有 manifest 的全部哈希")
    ap.add_argument("--self-test", action="store_true", help="反向证明额外文件会使集合守卫变红")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    if args.check:
        problems = check_manifest(manifest_path)
        if problems:
            print(f"未通过 {len(problems)} 条：")
            for problem in problems:
                print(f"  ✗ {problem}")
            return 1
        print(f"OK：v2 基线 manifest 与当前输入、产物、代码树、回归报告一致：{manifest_path}")
        return 0

    run_dir = resolve_run(args.run)
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = build(run_dir)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_text(manifest, manifest_path), encoding="utf-8")
    print(f"OK：v2 基线已写入 {manifest_path}")
    print(f"    人读摘要 {report_path}")
    print(f"    run={run_dir.name} code={manifest['version_identity']['sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
