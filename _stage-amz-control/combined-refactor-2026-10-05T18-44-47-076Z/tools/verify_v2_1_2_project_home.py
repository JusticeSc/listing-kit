#!/usr/bin/env python
"""V2.1.2 证据：空白项目首页与本机项目 CRUD（真实 Chromium + IndexedDB 后置条件）。

检查：
  1) 静态：app.js 通过 node --check。
  2) 空白启动：没有项目、没有指针、没有数据库，页面给出空白态。
  3) 新建：界面出现项目，IndexedDB 里有且只有一条，localStorage 仍为空。
  4) 打开：写入当前指针，刷新后仍在该项目；不产生新项目。
  5) 重命名：界面与 IndexedDB 同步，revision 递增。
  6) 复制：文档版本与资产 Blob 在新 project_id 下各存一份，原项目不变。
  7) 删除：记录与其文档/资产一起消失；作为当前项目时指针被清除。
  8) 两个独立浏览器配置文件互不可见；控制台零错误；390px 无横向溢出。
  9) 旧 Product V1 路由回归：默认入口页面与其静态资源仍可取（V2.1.2 不得破坏旧入口）。

运行：
  uv run --locked python tools/verify_v2_1_2_project_home.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from v2_test_server import start as start_server  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
DB_NAME = "amz-listing-kit-v2"
POINTER_KEY = "amz-listing-kit-v2:current-project"

DB_SNAPSHOT = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes("amz-listing-kit-v2")) {
    return { projects: [], documents: 0, assets: 0, db_exists: false };
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
    db_exists: true,
    projects: projects.map((item) => ({
      project_id: item.project_id, name: item.name, state: item.state, revision: item.revision,
    })),
    documents: documents.map((item) => ({
      project_id: item.project_id, kind: item.kind, document_id: item.document_id,
      version: item.version,
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

# 刷新后失败时，boot_error 为空 + 项目行数 0 + 指针仍在 这三种现象同时成立，
# 既可能是「脚本没执行」，也可能是「执行了但卡在某一步」——两者对判据都表现为
# #project-view 不出现。这段只在失败时读取，用来区分它们：
#   - 时间线里出现过 disabled=true  => boot() 确实执行过（HTML 默认无 disabled 属性）
#   - 没出现过                      => 模块没加载/没跑到第一行
#   - view_hidden / empty_hidden / project_view_seen 用来区分「卡在 refresh 之前」与
#     「refresh 完成了但 showProject 没跑」。
BOOT_TRAIL_SCRIPT = """
(() => {
  const trail = [];
  window.__bootTrail = trail;
  const now = () => Math.round(performance.now());
  // 必须从 init script 起就观察，不能等 DOMContentLoaded：模块脚本是 deferred，
  // 在 DOMContentLoaded 之前就已执行，boot() 的第一次 setHomeControlsBlocked(true)
  // 同步跑完后立刻 await；若观察器起晚了，true→false 这条轨迹会整段丢失，
  // 把「boot 已执行」误判成「脚本没执行」。
  const observer = new MutationObserver((records) => {
    for (const r of records) {
      if (r.target && r.target.id === 'create-project') {
        trail.push(['attr', r.oldValue, r.target.disabled, now()]);
      }
      if (r.target && r.target.id === 'project-view' && !r.target.hidden) {
        trail.push(['view-shown', now()]);
      }
    }
  });
  const attach = () => {
    if (document.documentElement) {
      observer.observe(document.documentElement, { subtree: true, attributes: true,
        attributeOldValue: true, attributeFilter: ['disabled', 'hidden'] });
      trail.push(['observing', document.readyState, now()]);
    } else {
      setTimeout(attach, 0);
    }
  };
  attach();
  window.addEventListener('error', (e) => {
    trail.push(['err', String((e && e.message) || e), now()]);
  });
  window.addEventListener('unhandledrejection', (e) => {
    trail.push(['reject', String((e && e.reason) || e), now()]);
  });
})();
"""

BOOT_STAGE_SNAPSHOT = """
() => ({
  trail: (window.__bootTrail || []).slice(-60),
  ready_state: document.readyState,
  create_has_disabled_attr: (document.getElementById('create-project') || {}).hasAttribute
    ? document.getElementById('create-project').hasAttribute('disabled') : null,
  project_view_hidden: (document.getElementById('project-view') || {}).hidden,
  empty_state_hidden: (document.getElementById('empty-state') || {}).hidden,
  rows: document.querySelectorAll('#project-list .project-row').length,
  // 直接回答「模块加载了吗」：本次文档里 app.js / workspace.js 有没有真的取到。
  resources: (performance.getEntriesByType('resource') || [])
    .filter((r) => /app\\.js|workspace\\.js|storage\\/index\\.js/.test(r.name))
    .map((r) => ({ name: r.name.split('/').pop(), ms: Math.round(r.duration),
                   bytes: r.transferSize || r.encodedBodySize || 0 })),
})
"""

SEED_DOCUMENT_AND_ASSET = """
async (projectId) => {
  const mod = await import("/storage/index.js");
  const opened = await mod.openStorage({});
  try {
    const doc = await opened.repository.documents.save(projectId, {
      kind: "product_input", documentId: "intake", payload: { note: "复制验证用资料" },
    });
    const asset = await opened.repository.assets.put(projectId, {
      bytes: new TextEncoder().encode("project-home-duplicate-bytes"),
      mediaType: "image/png", originalName: "ref.png", role: "primary",
    });
    return { version: doc.version, sha256: asset.sha256 };
  } finally {
    opened.close();
  }
}
"""


def run_node_check(path: Path) -> dict:
    completed = subprocess.run(["node", "--check", str(path)], cwd=ROOT, capture_output=True, text=True)
    return {"file": path.relative_to(ROOT).as_posix(), "rc": completed.returncode,
            "stderr": completed.stderr.strip()}


def check_v1_route() -> dict:
    """旧 Product V1 入口回归：在真实 V1 服务器上取默认页面与静态资源；只读，不碰工作空间。"""
    import threading
    import urllib.request

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.product_v1_server import create_product_server  # noqa: PLC0415

    server = create_product_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(base + "/", timeout=10) as response:
            page_status = response.status
            page_type = response.headers.get("Content-Type", "")
            page_body = response.read().decode("utf-8", "replace")
        with urllib.request.urlopen(base + "/product-assets/product.js", timeout=10) as response:
            asset_status = response.status
            asset_type = response.headers.get("Content-Type", "")
        ok = (page_status == 200 and asset_status == 200
              and "text/html" in page_type and "javascript" in asset_type
              and "/product-assets/product.js" in page_body)
        return {"ok": ok, "page_status": page_status, "asset_status": asset_status,
                "page_type": page_type, "asset_type": asset_type}
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.1.2 项目首页验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    node_result = run_node_check(ROOT / "app" / "product_v2" / "app.js")
    check("V2.1.2-00", "app.js 通过 node --check", node_result["rc"] == 0, node_result)

    server, base_url = start_server()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                # 失败时唯一能区分「boot 没跑」「boot 卡住」「boot 完成但视图没切」的证据。
                # 只观测，不参与任何判据：boot() 第一行 setHomeControlsBlocked(true) 会把
                # #create-project 置 disabled，HTML 默认无该属性，所以这条轨迹能证明脚本执行过。
                context.add_init_script(BOOT_TRAIL_SCRIPT)
                page = context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))

                # --- 空白启动 ---
                page.goto(base_url + "/", wait_until="networkidle")
                expect(page.locator("#empty-state")).to_be_visible()
                expect(page.locator("#project-list .project-row")).to_have_count(0)
                blank_db = page.evaluate(DB_SNAPSHOT)
                blank_pointer = page.evaluate(POINTER_SNAPSHOT)
                blank_png = EVIDENCE_DIR / f"v2.1.2-home-blank-{stamp}.png"
                EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(blank_png))
                screenshots.append(blank_png.relative_to(ROOT).as_posix())
                check(
                    "V2.1.2-01",
                    "空白启动：无项目、无指针、无预填内容",
                    blank_db["counts"]["projects"] == 0 and blank_pointer["keys"] == [],
                    {"db": blank_db["counts"], "pointer_keys": blank_pointer["keys"]},
                )

                # --- 新建（R3.3：新建即打开——写指针并进入工作台，与 handleOpen 同路径） ---
                page.fill("#new-project-name", "蓝色保温杯 秋季主图")
                page.click("#create-project")
                expect(page.locator("#project-view")).to_be_visible()
                expect(page.locator("#project-title")).to_have_text("蓝色保温杯 秋季主图")
                created_db = page.evaluate(DB_SNAPSHOT)
                created_pointer = page.evaluate(POINTER_SNAPSHOT)
                project_id = created_db["projects"][0]["project_id"]
                check(
                    "V2.1.2-02",
                    "新建即打开：IndexedDB 恰有一条 EMPTY 记录且当前指针已写入",
                    created_db["counts"]["projects"] == 1
                    and created_db["projects"][0]["state"] == "EMPTY"
                    and created_pointer["current"] is not None
                    and json.loads(created_pointer["current"])["project_id"] == project_id,
                    {"counts": created_db["counts"], "pointer": created_pointer["current"]},
                )

                # --- 回首页 + 打开 + 刷新（R3.3：boot 自动恢复指针项目并进入工作台） ---
                page.click("#back-home")
                expect(page.locator("#home-view")).to_be_visible()
                expect(page.locator("#project-list .project-row")).to_have_count(1)
                page.click("#project-list .project-row [data-action='open']")
                expect(page.locator("#project-view")).to_be_visible()
                expect(page.locator("#project-title")).to_have_text("蓝色保温杯 秋季主图")
                opened_pointer = page.evaluate(POINTER_SNAPSHOT)
                page.reload(wait_until="networkidle")
                # 2026-10-01 V2.7.1 全回归第一轮的真实教训：机器满载时 boot() 可能超过
                # Playwright 默认 5s 断言超时，界面停在「首页 + 空列表 + 控件未解锁」，
                # 看起来像「刷新后项目丢了」，其实是"还没启动完"；同一份数据在第二轮
                # 7s 内通过，单独重跑 8 次也全绿。这里先等"启动完成"（boot() 结束时
                # 才会解锁新建控件），再断言刷新恢复 —— 等的是启动就绪，不是放宽
                # 「刷新后仍在该项目」这条判据；失败时把诊断落盘，下一次不必再猜。
                try:
                    expect(page.locator("#create-project")).to_be_enabled(timeout=30_000)
                    expect(page.locator("#project-view")).to_be_visible(timeout=15_000)
                except AssertionError:
                    diagnostics = page.evaluate(
                        """async () => ({
                             boot_error: (document.getElementById('boot-error') || {}).textContent || '',
                             home_error: (document.getElementById('home-error') || {}).textContent || '',
                             create_disabled: (document.getElementById('create-project') || {}).disabled,
                             project_rows: document.querySelectorAll('#project-list .project-row').length,
                             pointer_keys: Object.keys(localStorage).sort(),
                             pointer: localStorage.getItem('amz-listing-kit-v2:current-project'),
                           })""")
                    diagnostics.update(page.evaluate(BOOT_STAGE_SNAPSHOT))
                    diagnostics["console_errors"] = console_errors
                    diagnostics["page_errors"] = page_errors
                    # 判读规则写进证据本身，避免下一次再靠猜：
                    #   boot 执行过 => 时间线含 'attr'（#create-project 的 disabled 变过，
                    #                   HTML 默认无该属性，只有 boot() 的
                    #                   setHomeControlsBlocked 会写它）
                    #   boot 没执行 => 只有 'observing'，且 has_disabled_attr 恒为 false
                    #   卡在哪一步  => 有 'view-shown' 说明 showProject 跑过；
                    #                   有 'err'/'reject' 说明模块期抛错
                    trail = diagnostics.get("trail") or []
                    seen = {entry[0] for entry in trail}
                    if "attr" in seen:
                        diagnostics["boot_judged"] = ("boot 执行过；"
                                                      + ("但项目视图从未可见 => 卡在 showProject 之前"
                                                         if "view-shown" not in seen
                                                         else "项目视图曾可见 => 与断言存在时序竞争"))
                    elif "view-shown" in seen:
                        diagnostics["boot_judged"] = "boot 执行过且视图曾可见"
                    elif "err" in seen or "reject" in seen:
                        diagnostics["boot_judged"] = "脚本抛错 => 见 trail 的 err/reject"
                    else:
                        diagnostics["boot_judged"] = "boot 未执行（模块没加载或没跑到第一行）"
                    diagnostics["module_loaded"] = any(
                        r.get("name") == "app.js" and r.get("bytes", 0) > 0
                        for r in diagnostics.get("resources") or [])
                    diag_path = EVIDENCE_DIR / f"v2.1.2-reload-diagnostics-{stamp}.json"
                    diag_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
                    print("刷新后未恢复 —— 诊断：" + json.dumps(diagnostics, ensure_ascii=False))
                    print("诊断落盘：" + diag_path.relative_to(ROOT).as_posix())
                    raise
                expect(page.locator("#project-title")).to_have_text("蓝色保温杯 秋季主图")
                after_reload = page.evaluate(DB_SNAPSHOT)
                check(
                    "V2.1.2-03",
                    "打开写入当前指针，刷新后仍在该项目且没有复制出第二个项目",
                    opened_pointer["current"] is not None
                    and after_reload["counts"]["projects"] == 1
                    and json.loads(opened_pointer["current"])["project_id"] == project_id,
                    {"pointer": opened_pointer["current"], "counts": after_reload["counts"]},
                )

                # --- 重命名 ---
                page.click("#back-home")
                page.click("#project-list .project-row [data-action='rename']")
                page.fill("#project-list .rename-input", "蓝色保温杯 主图套装")
                page.click("#project-list [data-action='rename-save']")
                expect(page.locator("#project-list .name")).to_have_text("蓝色保温杯 主图套装")
                renamed_db = page.evaluate(DB_SNAPSHOT)
                renamed = renamed_db["projects"][0]
                check(
                    "V2.1.2-04",
                    "重命名：界面与 IndexedDB 一致且 revision 递增",
                    renamed["name"] == "蓝色保温杯 主图套装" and renamed["revision"] == 2,
                    {"project": renamed},
                )

                # --- 复制（先给原项目塞入文档与资产） ---
                seeded = page.evaluate(SEED_DOCUMENT_AND_ASSET, project_id)
                page.reload(wait_until="networkidle")
                page.click("#back-home")
                page.click("#project-list .project-row [data-action='duplicate']")
                expect(page.locator("#project-list .project-row")).to_have_count(2)
                copied_db = page.evaluate(DB_SNAPSHOT)
                copy_id = next(item["project_id"] for item in copied_db["projects"]
                               if item["project_id"] != project_id)
                copy_docs = [item for item in copied_db["documents"] if item["project_id"] == copy_id]
                copy_assets = [item for item in copied_db["assets"] if item["project_id"] == copy_id]
                source_assets = [item for item in copied_db["assets"] if item["project_id"] == project_id]
                list_png = EVIDENCE_DIR / f"v2.1.2-home-list-{stamp}.png"
                page.screenshot(path=str(list_png))
                screenshots.append(list_png.relative_to(ROOT).as_posix())
                check(
                    "V2.1.2-05",
                    "复制：文档版本与资产在新 project_id 下各一份，原项目不变",
                    len(copy_docs) == 1 and len(copy_assets) == 1
                    and copy_assets[0]["sha256"] == seeded["sha256"]
                    and len(source_assets) == 1,
                    {"seed": seeded, "copy_docs": copy_docs, "copy_assets": copy_assets,
                     "source_assets": len(source_assets)},
                )

                # --- 删除（当前项目） ---
                page.click(
                    f"#project-list .project-row[data-project-id='{copy_id}'] [data-action='open']")
                expect(page.locator("#project-view")).to_be_visible()
                expect(page.locator("#project-title")).to_contain_text("（副本）")
                page.click("#back-home")
                page.click(
                    f"#project-list .project-row[data-project-id='{copy_id}'] [data-action='delete']")
                page.click("#project-list [data-action='delete-confirm']")
                expect(page.locator("#project-list .project-row")).to_have_count(1)
                deleted_db = page.evaluate(DB_SNAPSHOT)
                deleted_pointer = page.evaluate(POINTER_SNAPSHOT)
                check(
                    "V2.1.2-06",
                    "删除：记录、文档与资产一起消失，当前指针被清除",
                    deleted_db["counts"] == {"projects": 1, "documents": 1, "assets": 1}
                    and deleted_pointer["keys"] == [],
                    {"counts": deleted_db["counts"], "pointer_keys": deleted_pointer["keys"]},
                )

                # --- 390px 冒烟 ---
                page.set_viewport_size({"width": 390, "height": 844})
                page.reload(wait_until="networkidle")
                overflow = page.evaluate(
                    "() => document.documentElement.scrollWidth - window.innerWidth")
                check("V2.1.2-07", "390px 视口无横向溢出", overflow <= 1, {"overflow_px": overflow})
                context.close()

                # --- 两个配置文件互不可见 ---
                context_a = browser.new_context()
                context_b = browser.new_context()
                page_a = context_a.new_page()
                page_a.goto(base_url + "/", wait_until="networkidle")
                page_a.fill("#new-project-name", "隔离验证项目")
                page_a.click("#create-project")
                expect(page_a.locator("#project-view")).to_be_visible()
                expect(page_a.locator("#project-view")).to_contain_text("隔离验证项目")
                page_b = context_b.new_page()
                page_b.goto(base_url + "/", wait_until="networkidle")
                seen_in_b = page_b.locator("#project-list .project-row").count()
                pointer_b = page_b.evaluate(POINTER_SNAPSHOT)
                check(
                    "V2.1.2-08",
                    "两个独立浏览器配置文件的项目列表互不可见",
                    seen_in_b == 0 and pointer_b["keys"] == [],
                    {"projects_in_b": seen_in_b, "pointer_keys": pointer_b["keys"]},
                )
                context_a.close()
                context_b.close()

                check(
                    "V2.1.2-09",
                    "全程无 console error / page error",
                    not console_errors and not page_errors,
                    {"console_errors": console_errors, "page_errors": page_errors},
                )
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()

    # --- 旧 Product V1 路由回归（V2.1.2 不得破坏旧入口） ---
    v1_route = check_v1_route()
    check("V2.1.2-10", "旧 Product V1 路由未被破坏：默认入口页面与静态资源仍可取",
          v1_route["ok"], v1_route)

    failed = [item["id"] for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    report = {
        "task": "V2.1.2",
        "suite": "v2.1.2-project-home",
        "status": status,
        "finished_at": finished_at,
        "checks": checks,
        "screenshots": screenshots,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "boundary": (
            "证明项目首页与本机项目 CRUD：空白启动、列表、新建、打开、重命名、复制、删除、"
            "跨配置文件隔离、IndexedDB 后置条件与旧 Product V1 路由未被破坏。不证明项目 ZIP 导入导出、正式入口、"
            "商品资料/理解/套图/生成/交付，也不证明首次使用者可用性。"
        ),
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.1.2-project-home-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.1.2-project-home-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.1.2 project home contract",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False))
    lines += ["", "SCREENSHOTS"]
    lines += [f"- {item}" for item in screenshots]
    lines += ["", "BOUNDARY", report["boundary"]]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.1.2 项目首页验证")
    print("=" * 72)
    for item in checks:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            print("       " + json.dumps(item["detail"], ensure_ascii=False))
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
