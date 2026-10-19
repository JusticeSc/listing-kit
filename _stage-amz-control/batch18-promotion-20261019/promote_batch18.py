"""批次 8–17 的受控晋级：按规则暂存工作树改动，生成 promotion.json 证据。

规则(与批次 4/7 的 committable-paths 同族):
  keep   : 产品/工具/测试/配置/治理的已跟踪改动(含删除) + 批次证据目录
  drop   : chrome-profile/(本机浏览器配置) · _stage-amz-control 根目录的临时 .out/.log/.sh/.diff/文本
           · >20MB 的包(交付包/项目包再生成即可, 逐图字节与 manifest 已单独入库) · job*.log
  promote: evals/product-v2 下被 state/报告点名的最终证据(该目录默认 gitignore, 需 -f 精确晋级)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(".")
STAGE = "_stage-amz-control/"
PROMOTE = [
    "evals/product-v2/v2.7.1-regression-20261019-121022-final.json",
    "evals/product-v2/v2.4.5-live-reference-20261019-180800-b11-main-regenerate-ark-01.json",
    "evals/product-v2/v2.4.5-live-reference-20261019-180800-b11-main-regenerate-ark-01.txt",
    "evals/product-v2/v2.2.3-intake-understanding-20261019-211559.json",
    "evals/product-v2/v2.2.3-intake-understanding-20261019-211559.txt",
    "evals/product-v2/v2.2.3-workspace-20261019-211559.png",
    "evals/product-v2/v2.2.3-narrow-20261019-211559.png",
    "evals/product-v2/refactor/goal-observation-full-product-20261018T140710Z.json",
]


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def porcelain() -> list[str]:
    return git("status", "--porcelain=v1").splitlines()


def files_of(line: str) -> list[Path]:
    status, path = line[:2], line[3:]
    if status.strip() == "??":
        target = ROOT / path
        if target.is_dir():
            return [f for f in target.rglob("*") if f.is_file()]
        return [target]
    return [ROOT / path]


def bucket(f: Path) -> str:
    s = f.as_posix()
    if "chrome-profile" in f.parts:
        return "chrome-profile"
    if s.startswith(STAGE) and "/" not in s[len(STAGE):]:
        return "stage-root-scratch"
    if "/packages/" in s:
        return "package-zips>20MB"
    if s.endswith(".zip") and f.stat().st_size > 20_000_000:
        return "zips>20MB"
    if s.startswith("job") and s.endswith(".log"):
        return "raw-ci-log"
    return "keep"


def main() -> int:
    before = porcelain()
    counts: dict[str, int] = {}
    sizes: dict[str, int] = {}
    keep: list[Path] = []
    for line in before:
        for f in files_of(line):
            if line[:2].strip() != "??":
                keep.append(f)
                continue
            b = bucket(f)
            counts[b] = counts.get(b, 0) + 1
            sizes[b] = sizes.get(b, 0) + (f.stat().st_size if f.exists() else 0)
            if b == "keep":
                keep.append(f)

    # 1) 已跟踪改动（含删除）
    git("add", "-u")
    # 2) 批次证据目录（按文件逐个加，保证排除项不进 index）
    stage_batch = [f for f in keep if f.as_posix().startswith(STAGE) and f.exists()]
    for chunk in range(0, len(stage_batch), 200):
        git("add", "--", *[str(f) for f in stage_batch[chunk:chunk + 200]])
    # 3) 产品/测试/文档/配置的新文件
    others = [f for f in keep if not f.as_posix().startswith(STAGE) and f.exists()]
    for chunk in range(0, len(others), 200):
        git("add", "--", *[str(f) for f in others[chunk:chunk + 200]])
    # 4) 精确晋级被点名的 evals 证据
    promoted = []
    for path in PROMOTE:
        if (ROOT / path).exists():
            git("add", "-f", "--", path)
            promoted.append(path)

    staged = [line for line in porcelain() if line[:2] != "??"]
    staged_paths = sorted(line[3:].strip('"') for line in staged)
    eol = git("ls-files", "--eol", "--", *staged_paths) if staged_paths else ""
    crlf_index = [line for line in eol.splitlines() if line.startswith("i/crlf")]
    record = {
        "authority": "NOT-AUTHORITY: 晋级记录; 产品权威仍是 plan/design/state",
        "policy": {
            "keep": "产品/工具/测试/配置/治理已跟踪改动(含删除) + 批次证据目录(含截图/JSON/探针脚本)",
            "drop": ["chrome-profile/(本机浏览器配置)", "_stage-amz-control 根目录临时 .out/.log/.sh/.diff/文本",
                     "packages/*.zip 与 >20MB 的包(交付包/项目包; 逐图字节与 manifest 证据已另行入库)",
                     "job*.log(原始 CI 日志, 结论已写入 ci22-panel-assertion-20261019/evidence.json)"],
            "promote": "evals/product-v2 默认 gitignore 的最终证据按 state/报告点名精确 -f 晋级",
        },
        "dropped_counts": counts,
        "dropped_bytes": sizes,
        "promoted": promoted,
        "staged_count": len(staged_paths),
        "staged_index_crlf": crlf_index[:20],
        "staged_paths": staged_paths,
    }
    out = ROOT / STAGE / "batch18-promotion-20261019" / "promotion.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"staged {len(staged_paths)} paths; index CRLF files: {len(crlf_index)}")
    print("dropped:", {k: (v, f"{sizes.get(k,0)/1048576:.1f}MB") for k, v in counts.items() if k != "keep"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
