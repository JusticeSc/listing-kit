#!/usr/bin/env python3
"""NOT-AUTHORITY：在隔离 Git 仓库通过真实 CLI 验证文档拆分登记的来源与一次性重组证明。

只核对夹具内的提交、分片与登记；不读写实际仓库的文档、登记或 Git 配置。
--count 仅列出对照数。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Callable

CODE_ROOT = Path(__file__).resolve().parents[2]
GUARD = CODE_ROOT / "tools" / "check_document_splits.py"
SCRIPT = "tools/check_document_splits.py"
PROVENANCE_HELPER = CODE_ROOT / "tools" / "document_provenance.py"
REGISTRY_PATH = "config/document-splits.json"
PARENT = "docs/recovery.md"
FIRST_PART = "docs/recovery.01-history.md"
SECOND_PART = "docs/recovery.02-state.md"
STATE = "docs/recovery.yaml"
RAW_PARENT = "docs/record.txt"
RAW_PARTS = ("docs/record.01.txt", "docs/record.02.txt")
RAW_SEGMENTS = (b"first record\r\n", b"second record\r\n")
REPEAT_PARENT = "docs/repeat.txt"
REPEAT_PART = "docs/repeat.01.txt"
REPEAT_LINE = b"same line\r\n"
ORIGINAL = (
    "# 文档恢复记录\r\n"
    "\r\n"
    "## 已完成的拆分\r\n"
    "\r\n"
    "原件保存在 Git；文档可以继续修改。\r\n"
    "## 当前状态\r\n"
    "\r\n"
    "恢复证明完成后，继续维护下面的任务状态。\r\n"
    "```yaml\r\n"
    "schema: amz-probe-state/v1\r\n"
    "current:\r\n"
    "  task: document-recovery\r\n"
    "  status: running\r\n"
    "```\r\n"
).encode("utf-8")


@dataclass(frozen=True)
class Case:
    name: str
    change: Callable[[Path], None] | None = None
    arguments: tuple[str, ...] = ()
    expected: int = 0
    must: tuple[str, ...] = ()
    must_not: tuple[str, ...] = ()
    script: str = SCRIPT


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _environment(root: Path) -> dict[str, str]:
    # 不继承外部仓库、对象库、配置或模板；夹具提交不能触发用户 hooks。
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    environment.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TEMPLATE_DIR": str(root / "empty-hooks"), "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
    })
    return environment


def _git(root: Path, *arguments: str, payload: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", f"core.hooksPath={root / 'empty-hooks'}",
         "-c", "user.name=Document split probe", "-c", "user.email=doc-split-probe@example.invalid",
         *arguments], cwd=root, env=_environment(root), input=payload,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"夹具 Git {arguments!r} → rc={result.returncode}: "
                           + (result.stdout + result.stderr).decode("utf-8", "replace"))
    return result.stdout
def _remove_readonly(func: Callable[[str], None], path: str, _exc_info: object) -> None:
    """让 Windows 临时 Git 对象在夹具清理时可删除。"""
    os.chmod(path, 0o777)
    func(path)


def _put(root: Path, relative: str, payload: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _registry(root: Path) -> dict:
    return json.loads((root / REGISTRY_PATH).read_text(encoding="utf-8"))


def _write_registry(root: Path, registry: dict) -> None:
    _put(root, REGISTRY_PATH, (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _entry(root: Path, path: str) -> dict:
    return next(item for item in _registry(root)["splits"] if item["path"] == path)


def _put_part(root: Path, path: str, payload: bytes, parent: str | None = None) -> None:
    """写入分片并按它自己的字节更新登记，用来区分「分片变了」与「登记没跟上」。"""
    _put(root, path, payload)
    if parent is None:
        return
    registry = _registry(root)
    entry = next(item for item in registry["splits"] if item["path"] == parent)
    part = next(item for item in entry["parts"] if item["path"] == path)
    part.update({"bytes": len(payload), "sha256": _sha256(payload)})
    _write_registry(root, registry)


def _fixture(root: Path) -> None:
    root.mkdir()
    (root / "empty-hooks").mkdir()
    _put(root, SCRIPT, GUARD.read_bytes())
    _put(root, "tools/document_provenance.py", PROVENANCE_HELPER.read_bytes())
    _put(root, PARENT, ORIGINAL)
    _put(root, RAW_PARENT, b"".join(RAW_SEGMENTS))
    _put(root, REPEAT_PARENT, REPEAT_LINE * 2)
    _git(root, "init", "--quiet")
    _git(root, "add", "--", PARENT, RAW_PARENT, REPEAT_PARENT)
    _git(root, "commit", "--quiet", "--no-gpg-sign", "-m", "Preserve document originals")
    commit = _git(root, "rev-parse", "HEAD").strip().decode("ascii")
    # 临时夹具用自己的提交复现内容校验；候选仓库的固定公共基线由真实守卫另行覆盖。
    helper = root / "tools" / "document_provenance.py"
    helper.write_text(
        helper.read_text(encoding="utf-8").replace(
            'PUBLIC_BASELINE_COMMIT = "11902b32651f4690f7367624377dcde6652e0a97"',
            f'PUBLIC_BASELINE_COMMIT = "{commit}"',
        ),
        encoding="utf-8",
    )

    lines = ORIGINAL.splitlines(keepends=True)
    prefix = b"".join(lines[:2])
    parts = []
    continuation = "<!-- 续接：上一分片在此结束 -->\n".encode("utf-8")
    for number, relative, title, start, end in (
        (1, FIRST_PART, "已完成的拆分", 3, 5),
        (2, SECOND_PART, "当前状态", 6, 8),
    ):
        header = (
            f"<!-- 拆分件 {number:02d}/02 · 父文档 docs/recovery.md -->\n"
            f"# {title}\n[返回 recovery.md](recovery.md)\n\n"
        ).encode("utf-8")
        payload = header + (continuation if number == 2 else b"") + b"".join(lines[start - 1:end])
        _put(root, relative, payload)
        part = {"path": relative, "bytes": len(payload), "sha256": _sha256(payload)}
        if number == 2:
            # 续接标记是拆分时重复的导航行，重组前必须移除。
            part["remove_prefix"] = continuation.decode("utf-8")
        parts.append(part)
    state = b"".join(lines[9:13])
    _put(root, STATE, state)
    _put(root, PARENT, prefix + (
        "[恢复历史](recovery.01-history.md) / [当前状态](recovery.02-state.md)\n\n"
        "机器状态见 [recovery.yaml](recovery.yaml)。\n"
    ).encode("utf-8"))
    raw_parent_text = "See record.01.txt and record.02.txt in order.\n"
    _put(root, RAW_PARENT, raw_parent_text.encode("utf-8"))
    raw_parts = []
    for relative, payload in zip(RAW_PARTS, RAW_SEGMENTS):
        _put(root, relative, payload)
        raw_parts.append({"path": relative, "bytes": len(payload), "sha256": _sha256(payload)})
    # 节保留模式的父文档只是索引页：原文行由分片承担，父文档不再保有任何原文行。
    _put(root, REPEAT_PARENT, "[分片](repeat.01.txt)\n".encode("utf-8"))
    _put(root, REPEAT_PART, REPEAT_LINE * 2)
    _write_registry(root, {
        "schema": "amz-document-splits/v1",
        "splits": [{
            "path": PARENT,
            "mode": "byte-exact",
            "original": {"commit": commit, "path": PARENT, "bytes": len(ORIGINAL), "sha256": _sha256(ORIGINAL)},
            "prefix": {"lines": [1, 2], "sha256": _sha256(prefix)},
            "parts": parts,
            "extracted": [{
                "path": STATE, "lines": [10, 13], "bytes": len(state), "sha256": _sha256(state),
                "fences": {"open": "```yaml", "close": "```"},
            }],
        }, {
            "path": RAW_PARENT,
            "mode": "raw-parts",
            "original": {"commit": commit, "path": RAW_PARENT, "bytes": sum(map(len, RAW_SEGMENTS)),
                         "sha256": _sha256(b"".join(RAW_SEGMENTS))},
            "prefix": None,
            "parts": raw_parts,
        }, {
            "path": REPEAT_PARENT,
            "mode": "sections-preserved",
            "original": {"commit": commit, "path": REPEAT_PARENT, "bytes": len(REPEAT_LINE) * 2,
                         "sha256": _sha256(REPEAT_LINE * 2)},
            "prefix": None,
            "parts": [{"path": REPEAT_PART, "bytes": len(REPEAT_LINE) * 2,
                       "sha256": _sha256(REPEAT_LINE * 2)}],
        }],
    })


PROOF = ("--verify-current",)
PROVENANCE = ("来源与登记检查通过",)
RECONSTRUCTED = ("当前重组/保留证明通过",)


def _part_payload(root: Path, relative: str, replacement: tuple[bytes, bytes]) -> None:
    path = root / relative
    path.write_bytes(path.read_bytes().replace(*replacement))


def _edit_part(root: Path) -> None:
    _part_payload(root, FIRST_PART, ("文档可以继续修改。".encode("utf-8"), "文档已完成后续维护。".encode("utf-8")))


def _edit_part_and_hash(root: Path) -> None:
    _edit_part(root)
    _put_part(root, FIRST_PART, (root / FIRST_PART).read_bytes(), PARENT)


def _edit_parent(root: Path) -> None:
    _part_payload(root, PARENT, ("# 文档恢复记录".encode("utf-8"), "# 当前文档恢复记录".encode("utf-8")))


def _edit_state(root: Path) -> None:
    _part_payload(root, STATE, (b"schema: amz-probe-state/v1", b"schema: amz-probe-state/v2"))


def _remove_original_blob(root: Path) -> None:
    blob = _git(root, "rev-parse", f"HEAD:{PARENT}").strip().decode("ascii")
    object_path = root / ".git" / "objects" / blob[:2] / blob[2:]
    object_path.chmod(0o666)
    object_path.unlink()


def _pad_part(root: Path, size: int) -> None:
    payload = (root / FIRST_PART).read_bytes()
    _put_part(root, FIRST_PART, payload + b"x" * (size - len(payload)), PARENT)


def _drop_header(root: Path) -> None:
    payload = (root / FIRST_PART).read_bytes()
    _put_part(root, FIRST_PART, b"".join(payload.splitlines(keepends=True)[2:]), PARENT)


def _replace_header(root: Path) -> None:
    payload = (root / FIRST_PART).read_bytes()
    lines = payload.splitlines(keepends=True)
    _put_part(root, FIRST_PART, "# 普通小节\n".encode("utf-8") + b"".join(lines[1:]), PARENT)


def _edit_raw_part(root: Path) -> None:
    _put_part(root, RAW_PARTS[0], b"changed record\r\n", RAW_PARENT)


def _sections_incomplete_line(root: Path) -> None:
    # 原文两行相同，分片只保留一份：整行保留证明必须按次数判断。
    _put_part(root, REPEAT_PART, REPEAT_LINE, REPEAT_PARENT)


def _sections_line_inside_longer(root: Path) -> None:
    _put_part(root, REPEAT_PART, b"same line extended\r\n" * 2, REPEAT_PARENT)


def _sections_mode_for_raw(root: Path) -> None:
    registry = _registry(root)
    entry = next(item for item in registry["splits"] if item["path"] == RAW_PARENT)
    entry["mode"] = "sections-preserved"
    _write_registry(root, registry)


def _mismatched_original_digest(root: Path) -> None:
    registry = _registry(root)
    registry["splits"][0]["original"]["sha256"] = _sha256(b"different")
    _write_registry(root, registry)


def _branch_commit(root: Path) -> None:
    registry = _registry(root)
    registry["splits"][0]["original"]["commit"] = _git(root, "symbolic-ref", "--short", "HEAD").strip().decode()
    _write_registry(root, registry)


def _abbreviated_commit(root: Path) -> None:
    registry = _registry(root)
    registry["splits"][0]["original"]["commit"] = registry["splits"][0]["original"]["commit"][:12]
    _write_registry(root, registry)


def _escaping_part_path(root: Path) -> None:
    registry = _registry(root)
    registry["splits"][0]["parts"][0]["path"] = "../outside.md"
    _write_registry(root, registry)


def _absolute_original_path(root: Path) -> None:
    registry = _registry(root)
    registry["splits"][0]["original"]["path"] = "/etc/recovery.md"
    _write_registry(root, registry)


def _raw_parts_with_prefix(root: Path) -> None:
    registry = _registry(root)
    entry = next(item for item in registry["splits"] if item["path"] == RAW_PARENT)
    entry["prefix"] = {"lines": [1, 1], "sha256": _sha256(RAW_SEGMENTS[0])}
    _write_registry(root, registry)


def _duplicate_parent(root: Path) -> None:
    registry = _registry(root)
    registry["splits"].append(json.loads(json.dumps(registry["splits"][0])))
    _write_registry(root, registry)


def _duplicate_part(root: Path) -> None:
    registry = _registry(root)
    registry["splits"][0]["parts"][1]["path"] = FIRST_PART
    _write_registry(root, registry)


def _unsupported_mode(root: Path) -> None:
    registry = _registry(root)
    registry["splits"][0]["mode"] = "copied"
    _write_registry(root, registry)


def _wrong_schema(root: Path) -> None:
    registry = _registry(root)
    registry["schema"] = "amz-document-splits/v2"
    _write_registry(root, registry)


def _noncontiguous_extracted(root: Path) -> None:
    registry = _registry(root)
    entry = registry["splits"][0]
    segment = b"".join(ORIGINAL.splitlines(keepends=True)[10:13])
    entry["extracted"][0].update({
        "lines": [11, 13], "bytes": len(segment), "sha256": _sha256(segment),
        # 围栏也必须与新区间两侧的原文行一致，否则先触发围栏错误而掩盖区间判断。
        "fences": {"open": "schema: amz-probe-state/v1", "close": "```"},
    })
    _write_registry(root, registry)


def _wrong_fence(root: Path) -> None:
    registry = _registry(root)
    registry["splits"][0]["extracted"][0]["fences"]["open"] = "```yml"
    _write_registry(root, registry)


def _missing_registry(root: Path) -> None:
    (root / REGISTRY_PATH).unlink()


def _nested_script(root: Path) -> None:
    _put(root, "nested/" + SCRIPT, GUARD.read_bytes())
    _put(root, "nested/tools/document_provenance.py",
         (root / "tools/document_provenance.py").read_bytes())


def _cases() -> list[Case]:
    return [
        Case("A 默认核对原件来源与登记", must=PROVENANCE),
        Case("B 一次性 CRLF 重组与抽出的 YAML 围栏", arguments=PROOF, must=RECONSTRUCTED),
        Case("C 后续分片编辑不冻结", _edit_part, must=PROVENANCE),
        Case("D 分片变更使一次性证明失败", _edit_part, PROOF, 1,
             ("字节与拆分时登记的 sha256/bytes 不一致", "拆分件按序重组后与原件不一致")),
        Case("E 改写分片哈希仍不能伪造恢复", _edit_part_and_hash, PROOF, 1,
             ("拆分件按序重组后与原件不一致",), ("字节与拆分时登记的 sha256/bytes 不一致",)),
        Case("F 后续父文档编辑不冻结", _edit_parent, must=PROVENANCE),
        Case("G 父文档原文前缀变更使一次性证明失败", _edit_parent, PROOF, 1,
             (f"{PARENT}: 索引页前 2 行没有原样保留原文前缀",)),
        Case("H 后续机器状态编辑不冻结", _edit_state, must=PROVENANCE),
        Case("I 抽出的机器数据变更使一次性证明失败", _edit_state, PROOF, 1,
             (f"{STATE}: 字节与原件第 10-13 行不一致",)),
        Case("J 登记分片丢失", lambda root: (root / FIRST_PART).unlink(), expected=1,
             must=(f"{FIRST_PART}: 登记了但文件不存在",)),
        Case("K 原件 blob 丢失而提交与登记仍在", _remove_original_blob, expected=1,
             must=("无法从", f":{PARENT} 取回原件")),
        Case("L 登记的机器数据文件丢失", lambda root: (root / STATE).unlink(), expected=1,
             must=(f"{STATE}: 登记的机器数据文件不存在",)),
        Case("M 后续分片恰好 10000 字节", lambda root: _pad_part(root, 10_000), must=PROVENANCE),
        Case("N 后续分片 10001 字节越界", lambda root: _pad_part(root, 10_001), expected=1,
             must=(f"{FIRST_PART}: 10001 字节超过 10000 上限",),
             must_not=("字节与拆分时登记的 sha256/bytes 不一致",)),
        Case("O 拆分件不足 4 行导航头", _drop_header, expected=1, must=("4 行导航头",)),
        Case("P 拆分件首行不是导航头标记", _replace_header, expected=1, must=("4 行导航头",)),
        Case("Q 文本分片可继续编辑", _edit_raw_part, must=PROVENANCE),
        Case("R 更改文本分片和登记哈希仍无法伪造原件", _edit_raw_part, PROOF, 1,
             (f"{RAW_PARENT}: 文本分片按序重组后与原件不一致",),
             ("字节与拆分时登记的 sha256/bytes 不一致",)),
        Case("S 文本分片丢失", lambda root: (root / RAW_PARTS[1]).unlink(), expected=1,
             must=(f"{RAW_PARTS[1]}: 登记了但文件不存在",)),
        Case("T 原文行只是较长行的子串时不能证明保留", _sections_line_inside_longer, PROOF, 1,
             (f"{REPEAT_PARENT}: 2 行原文既不在索引页也不在拆分件中",)),
        Case("U 重复原文行少一次也不能证明保留", _sections_incomplete_line, PROOF, 1,
             (f"{REPEAT_PARENT}: 1 行原文既不在索引页也不在拆分件中",)),
        Case("V 节保留模式默认不冻结后续编辑", _sections_incomplete_line, must=PROVENANCE),
        Case("W 文本分片改用节保留模式后仍不冻结", _sections_mode_for_raw, must=PROVENANCE),
        Case("X 原件字节与登记不一致", _mismatched_original_digest, expected=1,
             must=(f"{PARENT}: 原件字节与登记的 original 不一致",)),
        Case("Y 分支名不能代替不可变提交", _branch_commit, expected=1,
             must=(f"{PARENT}: original.commit 必须是完整不可变提交 ID",)),
        Case("Z 缩写提交 ID 不可作为来源", _abbreviated_commit, expected=1,
             must=("original.commit 必须是完整不可变提交 ID",)),
        Case("AA 分片路径不能逃出仓库", _escaping_part_path, expected=1,
             must=("必须是仓库内相对路径",)),
        Case("AB 绝对原件路径拒绝", _absolute_original_path, expected=1,
             must=("必须是仓库内相对路径",)),
        Case("AC raw-parts 不能混入前缀或抽取", _raw_parts_with_prefix, expected=1,
             must=(f"{RAW_PARENT}: raw-parts 只能按序拼接 parts",)),
        Case("AD 父文档登记重复", _duplicate_parent, expected=1,
             must=(f"{PARENT}: 父文档登记重复",)),
        Case("AE 分片路径不能重复或指向父文档", _duplicate_part, expected=1,
             must=(f"{PARENT}: 拆分件路径不能重复或指向父文档",)),
        Case("AF 未知拆分模式", _unsupported_mode, expected=1, must=("mode 必须是",)),
        Case("AG 登记 schema 不受支持", _wrong_schema, expected=1,
             must=("registry schema 必须为 amz-document-splits/v1",)),
        Case("AH 抽取区间必须紧接前一段", _noncontiguous_extracted, PROOF, 1,
             must=("extracted 区间必须紧接前一段（起点应为 10）",)),
        Case("AI 代码围栏登记必须与原件一致", _wrong_fence, expected=1,
             must=("登记的代码围栏与原件不一致",)),
        Case("AJ 登记缺失", _missing_registry, expected=1, must=("document-splits.json",)),
        Case("AK 非 Git 根拒绝", lambda root: shutil.rmtree(root / ".git", onerror=_remove_readonly), expected=1,
             must=("公共 Git 来源不可用",)),
        Case("AL 嵌套脚本目录不能冒用祖先 Git 根", _nested_script, expected=1,
             must=("真实 Git 根不匹配",), script="nested/" + SCRIPT),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", action="store_true")
    arguments = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    cases = _cases()
    if arguments.count:
        print(len(cases))
        return 0
    failed = 0
    try:
        with tempfile.TemporaryDirectory(prefix="amz-document-splits-probe-") as directory:
            temporary = Path(directory)
            baseline = temporary / "baseline"
            _fixture(baseline)
            for number, case in enumerate(cases):
                root = temporary / f"case-{number:02d}"
                try:
                    shutil.copytree(baseline, root)
                    if case.change is not None:
                        case.change(root)
                    result = subprocess.run(
                        [sys.executable, "-B", str(root / case.script), *case.arguments],
                        cwd=root, env=_environment(root), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=60, check=False,
                    )
                    output = result.stdout + result.stderr
                    problems = []
                    if result.returncode != case.expected:
                        problems.append(f"退出码 {result.returncode}，期望 {case.expected}")
                    problems.extend(f"缺少 {item!r}" for item in case.must if item not in output)
                    problems.extend(f"不应出现 {item!r}" for item in case.must_not if item in output)
                    print(f"[{'FAIL' if problems else 'OK'}] {case.name} → rc={result.returncode}")
                    if problems:
                        failed += 1
                        print("\n".join(problems))
                        print(output.rstrip())
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                    failed += 1
                    print(f"[FAIL] {case.name}: {error}")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"[FAIL] 临时夹具建立或清理失败：{error}", file=sys.stderr)
        return 1
    print(f"{'FAIL' if failed else 'OK'}：{len(cases) - failed}/{len(cases)} 向符合预期；仅使用临时 Git 仓库。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
