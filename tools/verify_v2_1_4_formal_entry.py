#!/usr/bin/env python
"""V2.1.4 证据：Product V2 正式入口（无状态）与浏览器项目恢复。

检查：
  1) app/server.py 与 app/product_v2_server.py 通过语法自检。
  2) `python app/server.py --check` 正式入口自检全过（静态资源、health、拒绝 V1 工作空间 API 与目录逃逸）。
  3) `python app/server.py --legacy-v1 --check` Product V1 回归 6/6 保持。
  4) `python app/server.py --doctor` Product V2 体检 0 失败。
  5) 正式进程 HTTP 契约：/、/app.js、/storage/index.js 可取；V1 工作空间 API、harness、写接口 404。
  6) 磁盘审计：正式进程 + 浏览器完整会话前后，仓库受管目录与 %LOCALAPPDATA%/AMZ Listing Kit 零差异。
  7) 浏览器走查（真实 Chromium 持久 profile）：空白启动 → 新建项目 → 写入文档/资产 →
     关浏览器重开仍在 → 重启服务器后仍在。
  8) 网络审计：整个会话没有带 directory 的请求、没有 /api/workspaces、没有 /harness/，全部同源。
  9) 两个独立浏览器配置文件项目列表不同。
 10) 全程零 console error / page error；截图留证。

运行：
  & "C:\\Users\\31368\\.local\\bin\\uv.exe" run --no-project --with-requirements requirements.txt --with playwright python tools/verify_v2_1_4_formal_entry.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
APP_NAME = "V2.1.4"
PY = sys.executable

SCAN_DIRS = ("app", "demo", "src", "tools", "config")
SKIP_PARTS = {"__pycache__", ".uv-cache", ".git"}

DB_SNAPSHOT = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes("amz-listing-kit-v2")) {
    return { projects: [], documents: [], assets: [], counts: { projects: 0, documents: 0, assets: 0 } };
  }
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const read = (store) => new Promise((resolve, reject) => {
    const request = db.transaction(store, "readonly").objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const projects = await read("projects");
  const documents = await read("documents");
  const assets = await read("assets");
  db.close();
  return {
    projects: projects.map((item) => ({
      project_id: item.project_id, name: item.name, state: item.state, revision: item.revision,
    })),
    documents: documents.map((item) => ({
      project_id: item.project_id, kind: item.kind, document_id: item.document_id, version: item.version,
    })),
    assets: assets.map((item) => ({
      project_id: item.project_id, sha256: item.sha256, byte_size: item.byte_size,
    })),
    counts: { projects: projects.length, documents: documents.length, assets: assets.length },
  };
}
"""

POINTER_SNAPSHOT = """
() => ({
  keys: Object.keys(localStorage).sort(),
  current: localStorage.getItem("amz-listing-kit-v2:current-project"),
})
"""

SEED_DOCUMENT_AND_ASSET = """
async (projectId) => {
  const mod = await import("/storage/index.js");
  const opened = await mod.openStorage({});
  try {
    const doc = await opened.repository.documents.save(projectId, {
      kind: "product_input", documentId: "intake", payload: { note: "正式入口验证用资料" },
    });
    const asset = await opened.repository.assets.put(projectId, {
      bytes: new TextEncoder().encode("formal-entry-bytes-2026"),
      mediaType: "image/png", originalName: "ref.png", role: "primary",
    });
    return { version: doc.version, sha256: asset.sha256 };
  } finally {
    opened.close();
  }
}
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint() -> dict:
    """受管文件 + 根条目 + 最近项目索引目录；只做读操作。"""
    files: dict[str, dict] = {}
    for top in SCAN_DIRS:
        base = ROOT / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or SKIP_PARTS & set(path.parts) or path.suffix == ".pyc":
                continue
            stat = path.stat()
            entry = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            if stat.st_size <= 1 << 20:
                entry["sha256"] = sha256_file(path)
            files[path.relative_to(ROOT).as_posix()] = entry
    for path in sorted(ROOT.iterdir()):
        if path.is_file():
            stat = path.stat()
            entry = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            if stat.st_size <= 1 << 20:
                entry["sha256"] = sha256_file(path)
            files[f"./{path.name}"] = entry

    index_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "AMZ Listing Kit"
    index: dict = {"exists": index_dir.is_dir(), "files": {}}
    if index_dir.is_dir():
        for path in sorted(index_dir.rglob("*")):
            if path.is_file():
                stat = path.stat()
                index["files"][path.relative_to(index_dir).as_posix()] = {
                    "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                }
    return {"root_entries": sorted(p.name for p in ROOT.iterdir()),
            "files": files, "recent_index": index}


def diff_fingerprints(before: dict, after: dict) -> dict:
    added = sorted(set(after["files"]) - set(before["files"]))
    removed = sorted(set(before["files"]) - set(after["files"]))
    changed = sorted(name for name in set(before["files"]) & set(after["files"])
                     if before["files"][name] != after["files"][name])
    root_added = sorted(set(after["root_entries"]) - set(before["root_entries"]))
    root_removed = sorted(set(before["root_entries"]) - set(after["root_entries"]))
    index_changed = before["recent_index"] != after["recent_index"]
    return {"added": added, "removed": removed, "changed": changed,
            "root_added": root_added, "root_removed": root_removed,
            "recent_index_changed": index_changed,
            "clean": not (added or removed or changed or root_added or root_removed
                          or index_changed)}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class FormalServer:
    """以子进程启动正式入口；停止后端口必须释放。"""

    def __init__(self, port: int) -> None:
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.log_lines: list[str] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        self.proc = subprocess.Popen(
            [PY, "-B", str(ROOT / "app" / "server.py"), "--port", str(self.port)],
            cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("正式入口提前退出：" + (self.proc.stdout.read() or "")[-400:])
            try:
                with urllib.request.urlopen(self.base_url + "/api/health", timeout=2) as response:
                    if response.status == 200:
                        return
            except Exception:
                time.sleep(0.25)
        raise RuntimeError("正式入口 30 秒内没有就绪")

    def stop(self) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.log_lines.append(self.proc.communicate(timeout=15)[0] or "")
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.log_lines.append(self.proc.communicate(timeout=10)[0] or "")
        # 端口必须真的释放，才能证明重启用的是同一地址
        deadline = time.time() + 10
        while time.time() < deadline:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", self.port)) != 0:
                    return
            time.sleep(0.2)
        raise RuntimeError("停止后端口仍被占用")


def run_entry(args: list[str], timeout: int = 180) -> dict:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [PY, "-B", str(ROOT / "app" / "server.py"), *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )
    return {"args": args, "rc": completed.returncode,
            "tail": (completed.stdout + completed.stderr).strip().splitlines()[-6:]}


def http_status(base: str, path: str, method: str = "GET") -> tuple[int, str]:
    request = urllib.request.Request(base + path, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.1.4 正式入口验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    request_urls: list[str] = []
    screenshots: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    # --- 1. 语法自检 ---
    compile_results = []
    for target in ("app/server.py", "app/product_v2_server.py"):
        completed = subprocess.run([PY, "-B", "-m", "py_compile", str(ROOT / target)],
                                   cwd=str(ROOT), capture_output=True, text=True, check=False)
        compile_results.append({"file": target, "rc": completed.returncode,
                                "stderr": completed.stderr.strip()[-300:]})
    check(f"{APP_NAME}-00", "server.py 与 product_v2_server.py 通过语法自检",
          all(item["rc"] == 0 for item in compile_results), compile_results)

    # --- 2/3/4. 入口自检与体检（都在磁盘审计开始前）---
    v2_check = run_entry(["--check"])
    check(f"{APP_NAME}-01", "正式入口自检全过（静态资源 / health / 拒绝 V1 API 与目录逃逸）",
          v2_check["rc"] == 0 and any("13/13" in line for line in v2_check["tail"]), v2_check)

    v1_check = run_entry(["--legacy-v1", "--check"])
    check(f"{APP_NAME}-02", "Product V1 回归自检 6/6 保持（--legacy-v1）",
          v1_check["rc"] == 0 and any(line.strip() == "OK" for line in v1_check["tail"]), v1_check)

    doctor = run_entry(["--doctor"])
    check(f"{APP_NAME}-03", "V2 体检通过且声明服务器无用户状态",
          doctor["rc"] == 0 and any("可以启动" in line for line in doctor["tail"]), doctor)

    # --- 5. 磁盘审计开始：正式进程 + 浏览器完整会话前后零差异 ---
    before_fp = fingerprint()

    port = free_port()
    server = FormalServer(port)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v2-formal-"))
    profile_a = temp_root / "profile-a"
    profile_b = temp_root / "profile-b"
    evidence: dict = {}

    server.start()
    try:
        contract = {}
        for path, expect_code in (("/", 200), ("/app.js", 200), ("/styles.css", 200),
                                  ("/storage/index.js", 200), ("/api/health", 200),
                                  ("/api/workspaces/recent", 404),
                                  ("/harness/storage-contract.html", 404),
                                  ("/evals/probes/project_state.py", 404)):
            status, ctype = http_status(server.base_url, path)
            contract[path] = {"status": status, "type": ctype, "ok": status == expect_code}
        post_status, _ = http_status(server.base_url, "/api/workspaces", method="POST")
        contract["POST /api/workspaces"] = {"status": post_status, "ok": post_status in (404, 405)}
        _, home_type = http_status(server.base_url, "/")
        with urllib.request.urlopen(server.base_url + "/", timeout=10) as response:
            home_body = response.read().decode("utf-8", "replace")
        check(f"{APP_NAME}-04", "正式进程 HTTP 契约：产品资源可取，V1 工作空间 API / harness / 写接口不可达",
              all(item["ok"] for item in contract.values())
              and "Amazon US 商品套图" in home_body and "text/html" in home_type,
              contract)

        with sync_playwright() as pw:
            def attach(context):
                context.on("request", lambda request: request_urls.append(request.url))
                context.on("console", lambda message: console_errors.append(message.text)
                           if message.type == "error" else None)
                context.on("pageerror", lambda error: page_errors.append(str(error)))

            # --- 空白启动 + 新建 + 写入（持久 profile A）---
            with pw.chromium.launch_persistent_context(
                    str(profile_a), headless=True,
                    viewport={"width": 1280, "height": 900}) as ctx_a_first:
                attach(ctx_a_first)
                page = ctx_a_first.pages[0] if ctx_a_first.pages else ctx_a_first.new_page()
                page.goto(server.base_url + "/", wait_until="networkidle")
                expect(page.locator("#empty-state")).to_be_visible()
                expect(page.locator("#project-list .project-row")).to_have_count(0)
                blank_db = page.evaluate(DB_SNAPSHOT)
                blank_pointer = page.evaluate(POINTER_SNAPSHOT)
                blank_png = EVIDENCE_DIR / f"v2.1.4-formal-blank-{stamp}.png"
                EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(blank_png))
                screenshots.append(blank_png.relative_to(ROOT).as_posix())
                check(f"{APP_NAME}-05", "正式入口空白启动：无项目、无指针、无预填内容",
                      blank_db["counts"]["projects"] == 0 and blank_pointer["keys"] == [],
                      {"db": blank_db["counts"], "pointer_keys": blank_pointer["keys"]})

                page.fill("#new-project-name", "正式入口验证 · 保温杯")
                page.click("#create-project")
                expect(page.locator("#project-list .project-row")).to_have_count(1)
                created_db = page.evaluate(DB_SNAPSHOT)
                project_id = created_db["projects"][0]["project_id"]
                seeded = page.evaluate(SEED_DOCUMENT_AND_ASSET, project_id)
                seeded_db = page.evaluate(DB_SNAPSHOT)
                list_png = EVIDENCE_DIR / f"v2.1.4-formal-project-{stamp}.png"
                page.screenshot(path=str(list_png))
                screenshots.append(list_png.relative_to(ROOT).as_posix())
                check(f"{APP_NAME}-06", "新建项目并写入文档与资产（正式入口下走产品 storage 代码）",
                      created_db["counts"]["projects"] == 1 and seeded_db["counts"]["documents"] == 1
                      and seeded_db["counts"]["assets"] == 1
                      and seeded_db["assets"][0]["sha256"] == seeded["sha256"],
                      {"seed": seeded, "counts": seeded_db["counts"]})

            # --- 8（先做隔离，避免污染 A 的重开检查）：独立配置文件互不可见 ---
            with pw.chromium.launch_persistent_context(str(profile_b), headless=True,
                                                       viewport={"width": 1280, "height": 900}) as ctx_b:
                attach(ctx_b)
                page_b = ctx_b.pages[0] if ctx_b.pages else ctx_b.new_page()
                page_b.goto(server.base_url + "/", wait_until="networkidle")
                expect(page_b.locator("#project-list .project-row")).to_have_count(0)
                expect(page_b.locator("#empty-state")).to_be_visible()
                profile_b_db = page_b.evaluate(DB_SNAPSHOT)
            evidence["profile_b_projects"] = profile_b_db["counts"]["projects"]

            # --- 关浏览器重开：持久 profile 恢复 ---
            with pw.chromium.launch_persistent_context(str(profile_a), headless=True,
                                                       viewport={"width": 1280, "height": 900}) as ctx_a:
                attach(ctx_a)
                page_a = ctx_a.pages[0] if ctx_a.pages else ctx_a.new_page()
                page_a.goto(server.base_url + "/", wait_until="networkidle")
                expect(page_a.locator("#project-list .project-row")).to_have_count(1)
                expect(page_a.locator("#project-list .name")).to_have_text("正式入口验证 · 保温杯")
                reopened_db = page_a.evaluate(DB_SNAPSHOT)
                check(f"{APP_NAME}-07", "关浏览器重开后项目与资产 hash 恢复（IndexedDB 持久化）",
                      reopened_db["counts"] == seeded_db["counts"]
                      and reopened_db["assets"][0]["sha256"] == seeded["sha256"],
                      {"counts": reopened_db["counts"], "sha256": reopened_db["assets"][0]["sha256"]})

                # --- 服务器重启后刷新 ---
                server.stop()
                server.start()
                page_a.reload(wait_until="networkidle")
                expect(page_a.locator("#project-list .project-row")).to_have_count(1)
                after_restart_db = page_a.evaluate(DB_SNAPSHOT)
                check(f"{APP_NAME}-08", "重启服务器后刷新：项目与资产 hash 仍一致",
                      after_restart_db["counts"] == seeded_db["counts"]
                      and after_restart_db["assets"][0]["sha256"] == seeded["sha256"],
                      {"counts": after_restart_db["counts"],
                       "server_log_tail": server.log_lines[-1].strip().splitlines()[-3:]})

            check(f"{APP_NAME}-09", "两个独立浏览器配置文件项目列表不同",
                  profile_b_db["counts"]["projects"] == 0
                  and after_restart_db["counts"]["projects"] == 1,
                  {"profile_b": profile_b_db["counts"], "profile_a": after_restart_db["counts"]})

            same_origin = all(url.startswith(server.base_url) for url in request_urls)
            bad_urls = [url for url in request_urls
                        if "directory" in url.lower() or "/api/workspaces" in url.lower()
                        or "/harness/" in url.lower()]
            api_calls = [url for url in request_urls if "/api/" in url]
            check(f"{APP_NAME}-10", "网络审计：无 directory 参数、无 V1 工作空间 API、无 harness、全部同源",
                  same_origin and not bad_urls and set(api_calls) <= {server.base_url + "/api/health"},
                  {"requests": len(request_urls), "bad": bad_urls, "api": sorted(set(api_calls)),
                   "sample": request_urls[:6]})

            check(f"{APP_NAME}-11", "浏览器会话零 console error / page error",
                  not console_errors and not page_errors,
                  {"console": console_errors[:5], "page": page_errors[:5]})
    finally:
        server.stop()
        after_fp = fingerprint()

    disk_diff = diff_fingerprints(before_fp, after_fp)
    check(f"{APP_NAME}-12", "磁盘审计：正式进程 + 浏览器会话前后仓库与最近项目索引零差异",
          disk_diff["clean"],
          {"diff": disk_diff,
           "scanned": {"repo_dirs": list(SCAN_DIRS),
                       "root_entries": len(before_fp["root_entries"]),
                       "files": len(before_fp["files"]),
                       "recent_index_exists": before_fp["recent_index"]["exists"]}})

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明默认正式入口 `python app/server.py` 以无状态方式提供 Product V2 页面："
        "服务器不读写工作空间与最近项目索引、无 directory 参数、会话前后磁盘零差异；"
        "浏览器项目在关浏览器重开与服务器重启后从 IndexedDB 恢复；两个独立配置文件互不可见；"
        "Product V1 以 --legacy-v1 保留为回归入口且自检 6/6。"
        "不证明商品资料之后的业务链、真实模型调用、交付包、跨机器迁移与首次使用者可用性。"
    )
    report = {
        "task": APP_NAME,
        "suite": "v2.1.4-formal-entry",
        "status": status,
        "finished_at": finished_at,
        "port": port,
        "checks": checks,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "request_urls": request_urls,
        "screenshots": screenshots,
        "disk_diff": disk_diff,
        "boundary": boundary,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.1.4-formal-entry-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.1.4-formal-entry-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.1.4 formal entry (stateless server, browser-owned projects)",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        f"port: {port}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False))
    lines += ["", "SCREENSHOTS"]
    lines += [f"- {item}" for item in screenshots]
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.1.4 正式入口验证")
    print("=" * 72)
    for item in checks:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            print("       " + json.dumps(item["detail"], ensure_ascii=False)[:500])
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
