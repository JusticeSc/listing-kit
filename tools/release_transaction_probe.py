#!/usr/bin/env python
"""Product V2 发布事务探针：发布验收与事务机制的受控探针。

四种模式（都不读/写任何凭据文件，不做任何付费调用，不用 BYOK）：

  --page-smoke --base <url>
    对正式入口做真实验收：/api/health、/api/v2/capabilities、静态资源
    （/、styles.css、entry.js、app.js）的状态/类型/字节，再用已批准的 Playwright
    Chromium 无头 + 隔离临时配置验证实际启动/状态就绪/页面主链
    （安全上下文、WebCrypto、IndexedDB、新建/刷新、原生项目包下载/导入、零错误）。
    http(s)://127.0.0.1 或 localhost 按安全来源例外验收；
    https 按可信入口验收；其他明文地址按精确负例验收。

  --selftest
    真实调用 deploy/release-transaction.sh：一次性隔离容器/配置/HOME 上的
    脚本变异前失败（exit 1，原服务不变，无开放事务）/
    两个独立正式 Dockerfile 上下文（仅实际服务静态 marker A/B 不同）分别构建、
    先断言真实 image ID 不同（不用同一 image 换 tag 充数）/
    真实开放事务上的过期 finalize 拒绝（exit 4，previous 保留）/
    脏恢复点 deploy 拒绝（exit 1，不删 previous）/
    新版 health 绿但静态晚期失败时 finalize 重验证失败（exit 1，事务/previous/备份保留）/
    脚本 rollback 回到真实旧 image ID 与 marker A 并清除开放事务（exit 1）/
    再一轮新版成功 finalize 清理 previous 与事务，外加本地页面验收正反两极。
    初始旧服务基线为一次性 fixture（marker A 正式镜像）；被测迁移一律走脚本，不复制编排。
    缺 Docker/Playwright 时报 missing_prereq（exit 2）；构建失败保留真实输出判红（exit 1）。

  --fingerprint --runtime-root <directory> [--base <url>]
    输出实际运行文件与公开能力配置的 SHA256；可通过 docker exec stdin 在正式镜像内执行。
    只读取明确的代码/静态资源/模型配置与公开 capabilities，不读取 app.env 或私钥。

  --prerequisites
    只读报告 Linux 运行前提（Docker CLI/daemon、curl、Playwright），不启动容器/服务。

本探针 green 只证明探针条件下的机制成立，不证明某次真实部署已发布成功；
真实部署的回退仍需在对应发布事件后单独核对（见 deploy/release-transaction.sh）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_PREREQ = 2

# 主页状态探针复用 V2.UI.1 的既有形状（tools/verify_v2_ui_1_remote_entry.py）。
HOME_STATE_JS = """
() => {
  const notice = document.getElementById('capability-notice');
  const create = document.getElementById('create-project');
  const importTrigger = document.getElementById('import-trigger');
  const bootError = document.getElementById('boot-error');
  return {
    secure_context: window.isSecureContext === true,
    subtle_digest: typeof (crypto.subtle && crypto.subtle.digest),
    random_uuid: typeof crypto.randomUUID,
    indexeddb: typeof indexedDB,
    notice_hidden: notice ? notice.hidden : null,
    notice_gap: notice && notice.dataset ? (notice.dataset.errorGap || null) : null,
    notice_code: notice && notice.dataset ? (notice.dataset.errorCode || null) : null,
    boot_error_hidden: bootError ? bootError.hidden : null,
    project_names: Array.from(document.querySelectorAll('#project-list [data-role=name]'))
      .map((node) => node.textContent),
  };
}
"""


def emit(checks: list[dict], check_id: str, title: str, ok: bool, detail: object = None) -> None:
    checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
    print("  [{}] {} {}".format("PASS" if ok else "FAIL", check_id, title), flush=True)
    if not ok and detail is not None:
        print("       " + json.dumps(detail, ensure_ascii=False)[:2000], flush=True)


def fetch(base: str, path: str, timeout: int = 10) -> tuple[int, str, bytes]:
    url = base.rstrip("/") + path
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as error:
        return error.code, "", error.read()[:4096]
    except Exception as error:  # noqa: BLE001 - 连接失败记成状态 0，进入判红，不抛栈
        return 0, "", ("connection_failed:" + type(error).__name__).encode("utf-8")


def expected_capable(base: str) -> bool:
    split = urllib.parse.urlsplit(base)
    if split.scheme == "https":
        return True
    return split.hostname in ("127.0.0.1", "localhost", "::1")


def page_smoke(base: str, checks: list[dict], prefix: str = "PS") -> bool:
    """对 base 做真实的健康/资源/页面验收；返回是否全过。"""
    status, _, body = fetch(base, "/api/health")
    try:
        health = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        health = {}
    emit(checks, prefix + "-01", "健康检查表明服务器无业务状态",
         status == 200 and health.get("product") == "v2" and health.get("server_state") == "none",
         {"status": status, "body": health})

    status, _, body = fetch(base, "/api/v2/capabilities")
    try:
        caps = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        caps = {}
    images = caps.get("images") if isinstance(caps, dict) else None
    endpoints = (images or {}).get("endpoints") or []
    emit(checks, prefix + "-02", "能力查询可用且公共默认付费档关闭",
         status == 200 and caps.get("ok") is True and "/api/v2/images/submit" in endpoints
         and (images or {}).get("default_trial") == "closed",
         {"status": status, "ok": caps.get("ok"),
          "default_trial": (images or {}).get("default_trial"),
          "image_provider": ((images or {}).get("provider") or {}).get("provider_id")})

    status, ctype, body = fetch(base, "/")
    html = body.decode("utf-8", "replace")
    emit(checks, prefix + "-03", "首页外壳可达且含项目列表与应用入口标记",
         status == 200 and "text/html" in ctype and 'id="project-list"' in html,
         {"status": status, "content_type": ctype, "bytes": len(body),
          "sha256": hashlib.sha256(body).hexdigest()})

    status, ctype, body = fetch(base, "/styles.css")
    emit(checks, prefix + "-04", "样式资源可达、类型正确且非空",
         status == 200 and "text/css" in ctype and len(body) > 0,
         {"status": status, "content_type": ctype, "bytes": len(body),
          "sha256": hashlib.sha256(body).hexdigest()})

    for resource in ("/entry.js", "/app.js"):
        status, ctype, body = fetch(base, resource)
        emit(checks, prefix + "-05-" + resource[1:], "启动脚本可达且类型正确",
             status == 200 and "javascript" in ctype and len(body) > 0,
             {"resource": resource, "status": status, "content_type": ctype,
              "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        emit(checks, prefix + "-06", "页面主链（Playwright 可用）", False,
             {"missing_prereq": "playwright not installed; run uv sync --locked"})
        return all(item["ok"] for item in checks)

    capable = expected_capable(base)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        with sync_playwright() as pw:
            with tempfile.TemporaryDirectory(prefix="release-smoke-") as profile:
                # 与 tools/verify_v2_ui_1_remote_entry.py 同批准形状：先 Chrome
                # 通道，缺浏览器再退回默认 Chromium；不自建第二约定。
                try:
                    context = pw.chromium.launch_persistent_context(
                        profile, channel="chrome", headless=True,
                        viewport={"width": 1440, "height": 950})
                except Exception:
                    context = pw.chromium.launch_persistent_context(
                        profile, headless=True, viewport={"width": 1440, "height": 950})
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.set_default_timeout(30_000)
                    errors: list[str] = []
                    network: list[str] = []
                    expected_netloc = urllib.parse.urlsplit(base).netloc
                    page.on("console", lambda message: errors.append("console:" + message.text)
                            if message.type == "error" else None)
                    page.on("pageerror", lambda error: errors.append("pageerror:" + str(error)))

                    def on_response(response) -> None:
                        split = urllib.parse.urlsplit(response.url)
                        if split.scheme in ("http", "https") and split.netloc != expected_netloc:
                            network.append("cross-origin:" + response.url)
                        if response.status >= 400:
                            network.append("status:" + str(response.status) + " " + response.url)

                    page.on("response", on_response)
                    page.goto(base + "/", wait_until="load", timeout=45000)
                    if capable:
                        page.wait_for_selector("#create-project:not([disabled])")
                    state = page.evaluate(HOME_STATE_JS)
                    if capable:
                        ok_boot = (state["secure_context"] is True
                                   and state["subtle_digest"] == "function"
                                   and state["random_uuid"] == "function"
                                   and state["indexeddb"] == "object"
                                   and state["notice_hidden"] is True
                                   and state["boot_error_hidden"] is True)
                        emit(checks, prefix + "-06", "页面实际启动：安全上下文与能力齐备且无工程诊断",
                             ok_boot, state)
                        name = "release-smoke " + stamp
                        page.fill("#new-project-name", name)
                        page.click("#create-project")
                        page.wait_for_selector("#project-view:not([hidden])")
                        page.click("#back-home")
                        page.wait_for_selector("#project-list .project-row", timeout=20000)
                        created = name in (page.evaluate(HOME_STATE_JS).get("project_names") or [])
                        page.reload(wait_until="load")
                        page.wait_for_selector("#project-view:not([hidden])")
                        page.click("#back-home")
                        page.wait_for_selector("#project-list .project-row", timeout=20000)
                        after = page.evaluate(HOME_STATE_JS)
                        emit(checks, prefix + "-07", "隔离项目新建后刷新仍在（IndexedDB 后置条件）",
                             created and name in (after.get("project_names") or []),
                             {"created": created, "after": after.get("project_names")})
                        source_ids = page.locator("#project-list .project-row").evaluate_all(
                            "rows => rows.map(row => row.dataset.projectId)")
                        row = page.locator("#project-list .project-row").filter(has_text=name)
                        with page.expect_download(timeout=30000) as pending_download:
                            row.locator('button[data-action="export"]').focus()
                            page.keyboard.press("Enter")
                        download = pending_download.value
                        package = Path(profile) / "downloaded-project.zip"
                        download.save_as(str(package))
                        with zipfile.ZipFile(package) as archive:
                            if archive.testzip() is not None:
                                raise ValueError("native project ZIP has a corrupt member")
                        with package.open("rb") as stream:
                            package_sha = hashlib.file_digest(stream, "sha256").hexdigest()
                        page.set_input_files("#import-file", str(package))
                        page.wait_for_function(
                            "original => document.querySelectorAll('#project-list .project-row').length"
                            " === original.length + 1", arg=source_ids)
                        imported_ids = page.locator("#project-list .project-row").evaluate_all(
                            "rows => rows.map(row => row.dataset.projectId)")
                        page.reload(wait_until="load")
                        page.wait_for_selector("#project-view:not([hidden])")
                        page.click("#back-home")
                        page.wait_for_function(
                            "expected => { const ids = Array.from(document.querySelectorAll("
                            "'#project-list .project-row'), row => row.dataset.projectId);"
                            " return ids.length === expected.length && expected.every(id => ids.includes(id)); }",
                            arg=imported_ids)
                        restored_names = page.evaluate(HOME_STATE_JS)["project_names"]
                        emit(checks, prefix + "-07-package", "原生下载/导入分配独立身份并在刷新后恢复",
                             set(source_ids).issubset(imported_ids)
                             and len(set(imported_ids) - set(source_ids)) == 1
                             and len([value for value in restored_names if value == name]) == 2,
                             {"original_ids": source_ids, "restored_ids": imported_ids,
                              "zip_sha256": package_sha, "zip_bytes": package.stat().st_size})
                    else:
                        ok_negative = (state["secure_context"] is False
                                       and state["notice_hidden"] is False
                                       and state["notice_gap"] == "secure_context")
                        emit(checks, prefix + "-06", "明文非本地入口精确报安全上下文缺口",
                             ok_negative, state)
                        emit(checks, prefix + "-07", "负例不建项目（跳过）", True, {"skipped": True})
                    emit(checks, prefix + "-08", "页面会话零 console/page/网络错误",
                         not errors and not network, {"console": errors, "network": network})
                finally:
                    context.close()
    except Exception as error:  # noqa: BLE001 - 探针必须把浏览器失败记成 FAIL，不抛栈
        emit(checks, prefix + "-06", "页面主链（浏览器实际运行）", False,
             {"error": type(error).__name__ + ": " + str(error)[:500]})
        return False
    return all(item["ok"] for item in checks)


def docker(*argv: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *argv], capture_output=True, text=True, timeout=timeout)


def docker_exists(name: str) -> bool:
    return docker("container", "inspect", name).returncode == 0


def docker_image_id(ref: str) -> str:
    """不可变镜像身份：image ID（sha256: 完整 ID），不是可变的 tag 名。"""
    result = docker("images", "--no-trunc", "-q", ref)
    bare = result.stdout.strip().split()[0] if result.returncode == 0 and result.stdout.strip() else ""
    if not bare:
        return ""
    return bare if bare.startswith("sha256:") else "sha256:" + bare


def container_image_id(name: str) -> str:
    """运行中容器的不可变镜像身份：`docker inspect .Image` 的 sha256 ID。"""
    result = docker("inspect", "--format", "{{.Image}}", name)
    value = result.stdout.strip() if result.returncode == 0 else ""
    return value if value.startswith("sha256:") else ""


def served_marker(base: str) -> str:
    """实际服务字节里的版本 marker：必须读已部署容器的真实响应，不能看本地文件。"""
    status, _, body = fetch(base, "/release-marker.txt")
    if status != 200:
        return ""
    try:
        return body.decode("utf-8").strip()
    except UnicodeDecodeError:
        return ""


def wait_healthy(name: str, tries: int = 45) -> bool:
    for _ in range(tries):
        result = docker("inspect", "--format", "{{.State.Health.Status}}", name)
        status = result.stdout.strip()
        if status == "healthy":
            return True
        if status == "unhealthy":
            return False
        time.sleep(2)
    return False


def run_script(*argv: str, timeout: int = 600,
               env: dict | None = None) -> subprocess.CompletedProcess[str]:
    """真实执行仓库的 deploy/release-transaction.sh（事务逻辑本身，不用 mock 回声）。"""
    script = ROOT / "deploy" / "release-transaction.sh"
    return subprocess.run(["bash", str(script), *argv],
                          capture_output=True, text=True, timeout=timeout, env=env)


def selftest() -> int:
    """在隔离 HOME/容器/本地 CA 上执行正式发布事务，不复制事务编排。
    两个独立正式 Dockerfile 上下文分别构建真实旧/新镜像（仅实际服务静态 marker A/B 不同），
    正式上下文复用仓库 Dockerfile/.dockerignore，不另建运行栈。
    本地 Caddy CA 仅传给探针子进程，不安装到宿主信任库、不跳过 TLS 验证。
    """
    print("=" * 72)
    print("发布事务自检：正式镜像 + 隔离服务/TLS + 真实事务脚本")
    print("=" * 72)
    checks: list[dict] = []
    if shutil.which("docker") is None or docker("info").returncode != 0:
        emit(checks, "ST-01", "Docker 可用", False, {"missing_prereq": "Docker daemon unavailable"})
        return EXIT_PREREQ
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415,F401
    except ImportError:
        emit(checks, "ST-01", "Playwright 可用", False, {"missing_prereq": "Playwright absent"})
        return EXIT_PREREQ
    emit(checks, "ST-01", "Docker 与 Playwright 可用", True)

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    old_tag = "amz-release-probe-old:" + stamp
    new_tag = "amz-release-probe-new:" + stamp
    # 两个独立正式上下文的实际服务静态 marker：仅此字节不同，保证两个真实 image ID 不同。
    # marker 只写进一次性构建上下文，不进仓库正式源树。
    marker_a = "release-marker-a-" + stamp + "\n"
    marker_b = "release-marker-b-" + stamp + "\n"
    app = "amz-release-probe-app-" + stamp
    tls = app + "-tls"
    previous = app + "-previous"
    volumes = [app + "-caddy-data", app + "-caddy-config"]
    tmp = Path(tempfile.mkdtemp(prefix="release-tx-"))
    fake_home = tmp / "home"
    release_dir = fake_home / ".config" / "amz-listing-kit"
    live_caddy = release_dir / "tls" / "Caddyfile"
    transaction = release_dir / "deploy-transaction.env"
    app_port, https_port = 18780, 18443
    contexts: list[Path] = []
    script_env = dict(os.environ, HOME=str(fake_home))
    ca_file = tmp / "probe-ca.crt"
    script_env["CURL_CA_BUNDLE"] = str(ca_file)

    def caddy_config(marker: str, *, broken_static: bool = False) -> str:
        handlers = (
            "\thandle /api/health {\n\t\treverse_proxy 127.0.0.1:%d\n\t}\n"
            '\thandle {\n\t\trespond "fixture missing product shell" 200\n\t}\n' % app_port
            if broken_static else "\treverse_proxy 127.0.0.1:%d\n" % app_port
        )
        return ("https://127.0.0.1:%d {\n\ttls internal\n\theader X-Release-Fixture %s\n%s}\n"
                % (https_port, marker, handlers))

    def prepare_context(*, missing_script: bool = False, marker: str | None = None) -> Path:
        context = Path(tempfile.mkdtemp(prefix="amz-listing-kit-0", dir="/tmp"))
        contexts.append(context)
        for name in ("Dockerfile", ".dockerignore", "pyproject.toml", "uv.lock"):
            shutil.copy2(ROOT / name, context / name)
        for name in ("app", "src", "config", "deploy"):
            shutil.copytree(ROOT / name, context / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        # 独立上下文的唯一有意差异：实际服务的静态 marker A/B。
        # marker 文件必须落进正式 PRODUCT_DIR（app/product_v2/），使构建产物与服务字节真实不同。
        if marker is not None:
            (context / "app" / "product_v2" / "release-marker.txt").write_text(marker, encoding="utf-8")
        candidate = context / "deploy" / "caddy" / "Caddyfile"
        candidate.write_text(caddy_config("new"), encoding="utf-8")
        if missing_script:
            (context / "deploy" / "release-transaction.sh").unlink()
        return context

    def argv(context: Path) -> list[str]:
        return [new_tag, app, str(app_port), str(context), "127.0.0.1", str(https_port)]

    def trusted_health() -> bool:
        response = subprocess.run(
            ["curl", "--fail", "--silent", "--show-error", "--max-time", "5",
             "https://127.0.0.1:%d/api/health" % https_port],
            capture_output=True, text=True, timeout=10, env=script_env)
        if response.returncode != 0:
            return False
        try:
            payload = json.loads(response.stdout)
            return payload.get("product") == "v2" and payload.get("server_state") == "none"
        except (ValueError, AttributeError):
            return False

    def record(check_id: str, title: str, ok: bool,
               result: subprocess.CompletedProcess[str] | None = None) -> bool:
        detail = None if result is None else {
            "rc": result.returncode, "stderr": result.stderr[-1500:],
            "serving_image_id": container_image_id(app),
            "previous_image_id": container_image_id(previous) if docker_exists(previous) else "",
            "transaction_exists": transaction.is_file(),
        }
        emit(checks, check_id, title, ok, detail)
        return ok

    try:
        old_context = prepare_context(marker=marker_a)
        built_old = docker("build", "--tag", old_tag, str(old_context), timeout=600)
        if not record("ST-02-A", "旧版正式 Dockerfile 独立上下文真实构建（marker A）",
                      built_old.returncode == 0, built_old):
            return EXIT_FAILED
        new_context = prepare_context(marker=marker_b)
        built_new = docker("build", "--tag", new_tag, str(new_context), timeout=600)
        if not record("ST-02-B", "新版正式 Dockerfile 独立上下文真实构建（marker B）",
                      built_new.returncode == 0, built_new):
            return EXIT_FAILED
        old_id = docker_image_id(old_tag)
        new_id = docker_image_id(new_tag)
        served_base = "http://127.0.0.1:%d" % app_port
        ids_differ = bool(old_id) and bool(new_id) and old_id != new_id
        emit(checks, "ST-02-IDs", "两轮真实 image ID 不同（不用同一 image 换 tag 充数）",
             ids_differ, {"old_tag": old_tag, "new_tag": new_tag,
                          "old_image_id": old_id, "new_image_id": new_id})
        if not ids_differ:
            return EXIT_FAILED
        baseline = docker("run", "--detach", "--name", app, "--publish",
                          "127.0.0.1:%d:8780" % app_port, old_tag)
        if not record("ST-03", "隔离旧服务基线健康且实际 marker 为 A",
                      baseline.returncode == 0 and wait_healthy(app)
                      and served_marker(served_base) == marker_a.strip(), baseline):
            emit(checks, "ST-03-marker", "基线实际 marker", False,
                 {"expected": marker_a.strip(), "served": served_marker(served_base)})
            return EXIT_FAILED
        live_caddy.parent.mkdir(parents=True, exist_ok=True)
        old_config = caddy_config("old")
        live_caddy.write_text(old_config, encoding="utf-8")
        proxy = docker("run", "--detach", "--name", tls, "--network", "host",
                       "--volume", "%s:/etc/caddy/Caddyfile:ro" % live_caddy,
                       "--volume", volumes[0] + ":/data",
                       "--volume", volumes[1] + ":/config", "caddy:2")
        if proxy.returncode != 0:
            record("ST-03-TLS", "隔离 TLS 基线启动", False, proxy)
            return EXIT_FAILED
        for _ in range(30):
            copied = docker("cp", tls + ":/data/caddy/pki/authorities/local/root.crt", str(ca_file))
            if copied.returncode == 0 and trusted_health():
                break
            time.sleep(1)
        if not record("ST-03-TLS", "显式信任隔离 CA 的 HTTPS 基线", trusted_health()):
            return EXIT_FAILED

        early = run_script("deploy", *argv(prepare_context(missing_script=True)), env=script_env)
        if not record("ST-04", "变异前失败保留原服务/TLS且无开放事务",
                      early.returncode == 1 and container_image_id(app) == old_id
                      and served_marker(served_base) == marker_a.strip()
                      and not docker_exists(previous) and not transaction.exists()
                      and live_caddy.read_text(encoding="utf-8") == old_config
                      and trusted_health(), early):
            return EXIT_FAILED

        context = prepare_context(marker=marker_b)
        release_args = argv(context)
        deployed = run_script("deploy", *release_args, env=script_env)
        if not record("ST-05", "真实 deploy 开放事务并保留旧容器/配置",
                      deployed.returncode == 0
                      and container_image_id(app) not in ("", old_id)
                      and container_image_id(previous) == old_id and transaction.is_file()
                      and (live_caddy.parent / "Caddyfile.release-backup").is_file()
                      and served_marker(served_base) == marker_b.strip()
                      and trusted_health(), deployed):
            return EXIT_FAILED
        new_id = docker_image_id(new_tag) or container_image_id(app)
        stale_args = [new_tag + "-stale", *release_args[1:]]
        stale = run_script("finalize", *stale_args, env=script_env)
        if not record("ST-05-stale", "过期 finalize 拒绝且保留真实恢复点",
                      stale.returncode == 4 and container_image_id(previous) == old_id
                      and transaction.is_file() and trusted_health(), stale):
            return EXIT_FAILED

        saved_transaction = transaction.read_bytes()
        transaction.unlink()
        try:
            dirty = run_script("deploy", *argv(prepare_context(marker=marker_b)), env=script_env)
            dirty_ok = (dirty.returncode == 1 and container_image_id(app) == new_id
                        and container_image_id(previous) == old_id and not transaction.exists()
                        and served_marker(served_base) == marker_b.strip()
                        and trusted_health())
        finally:
            transaction.write_bytes(saved_transaction)
        if not record("ST-05-dirty", "脏恢复点拒绝部署且不删任一容器", dirty_ok, dirty):
            return EXIT_FAILED

        live_caddy.write_text(caddy_config("new", broken_static=True), encoding="utf-8")
        restarted = docker("restart", tls)
        if restarted.returncode != 0:
            record("ST-06-inject", "真实注入健康API/坏静态入口", False, restarted)
            return EXIT_FAILED
        for _ in range(15):
            if trusted_health():
                break
            time.sleep(1)
        failed = run_script("finalize", *release_args, env=script_env)
        backup_path = live_caddy.parent / "Caddyfile.release-backup"
        if not record("ST-06", "新版 health 绿但坏静态 finalize 判红且 previous/journal/备份保留",
                      failed.returncode == 1 and container_image_id(previous) == old_id
                      and transaction.is_file() and backup_path.is_file()
                      and live_caddy.read_text(encoding="utf-8") != old_config
                      and served_marker(served_base) == marker_b.strip()
                      and trusted_health(), failed):
            return EXIT_FAILED
        rolled = run_script("rollback", *release_args, "acceptance_failed", env=script_env)
        if not record("ST-07", "实际回退回到真实旧 image ID/marker A 并清除事务",
                      rolled.returncode == 1 and container_image_id(app) == old_id
                      and served_marker(served_base) == marker_a.strip()
                      and not docker_exists(previous) and not transaction.exists()
                      and live_caddy.read_text(encoding="utf-8") == old_config
                      and trusted_health(), rolled):
            return EXIT_FAILED

        context = prepare_context(marker=marker_b)
        release_args = argv(context)
        deployed = run_script("deploy", *release_args, env=script_env)
        if deployed.returncode != 0:
            record("ST-08-deploy", "收口前候选重新部署", False, deployed)
            return EXIT_FAILED
        new_id = docker_image_id(new_tag) or container_image_id(app)
        finalized = run_script("finalize", *release_args, env=script_env)
        if not record("ST-08", "成功 finalize 清除恢复点且保留健康新服务（真实新 image ID/marker B）",
                      finalized.returncode == 0 and container_image_id(app) == new_id
                      and served_marker(served_base) == marker_b.strip()
                      and not docker_exists(previous) and not transaction.exists()
                      and not (live_caddy.parent / "Caddyfile.release-backup").exists()
                      and trusted_health(), finalized):
            return EXIT_FAILED

        sys.path.insert(0, str(ROOT / "tools"))
        from v2_test_server import start as start_server  # noqa: PLC0415
        server, local_base = start_server()
        try:
            live_ok = page_smoke(local_base, checks, prefix="ST-LIVE")
        finally:
            server.shutdown()
            server.server_close()
        dead_checks: list[dict] = []
        dead_ok = page_smoke("http://127.0.0.1:9", dead_checks, prefix="ST-DEAD")
        record("ST-09", "页面验收对不可达入口判红", not dead_ok)
        record("ST-10", "页面验收对真实产品页面判绿", live_ok)
    finally:
        for name in (app, previous, tls):
            if docker_exists(name):
                docker("rm", "--force", name)
        for name in (old_tag, new_tag):
            docker("rmi", "--force", name)
        for name in volumes:
            docker("volume", "rm", name)
        for context in contexts:
            shutil.rmtree(context, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
    failed_checks = [item["id"] for item in checks if not item["ok"]]
    print("结果：%d/%d 通过，%d 失败。" %
          (len(checks) - len(failed_checks), len(checks), len(failed_checks)), flush=True)
    return EXIT_FAILED if failed_checks else EXIT_OK


def runtime_fingerprint(root: Path, base: str) -> int:
    """生产容器内执行的只读指纹；不存在的必需运行文件不能变成空树成功。

    覆盖：全部 Python 网关/适配器（src）、公开模型配置与锁文件、
    公开能力配置，再核对实际服务且已生成的浏览器 JS、服务镜像 ID/tag、Caddy hash。
    secret 永不取 hash、不输出。
    """
    root = root.resolve()
    files: dict[str, str] = {}

    def include(path: Path) -> None:
        relative = path.relative_to(root).as_posix()
        if relative not in files:
            with path.open("rb") as stream:
                files[relative] = hashlib.file_digest(stream, "sha256").hexdigest()

    # 显式必需运行文件：缺任一都直接失败，不变成空树成功。
    required = ("pyproject.toml", "uv.lock", "app/server.py",
                "app/product_v2_server.py", "app/product_v2/entry.js",
                "config/product-v2/providers.json")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise RuntimeError("required runtime files missing: " + ",".join(missing))
    for name in required:
        include(root / name)
    suffixes = {".py", ".js", ".mjs", ".css", ".html", ".json", ".yaml", ".yml",
                ".toml", ".svg", ".png", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".txt"}
    for directory in ("app", "src", "config"):
        for path in (root / directory).rglob("*"):
            if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts:
                # 运行产物集合：TS 源与类型声明不在 suffixes 内，不进镜像也不进指纹。
                relative = path.relative_to(root).as_posix()
                lowered = relative.lower()
                if "secret" in lowered or "app.env" in lowered:
                    raise RuntimeError("refusing to fingerprint secret material: " + relative)
                include(path)
    # 实际服务且已生成的浏览器 JS：只认 HTTP 200 的真实服务字节，不认本地同名文件。
    served_scripts: dict[str, str] = {}
    for resource in ("/entry.js", "/app.js"):
        status, ctype, body = fetch(base, resource)
        if status != 200 or "javascript" not in ctype or not body:
            raise RuntimeError("served generated script unavailable: " + resource)
        served_scripts[resource] = hashlib.sha256(body).hexdigest()
    status, _, body = fetch(base, "/api/v2/capabilities")
    capabilities = json.loads(body)
    if status != 200 or capabilities.get("ok") is not True:
        raise RuntimeError("public runtime capabilities unavailable")
    configuration = hashlib.sha256(json.dumps(
        capabilities, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    runtime = hashlib.sha256(json.dumps(
        files, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    print(json.dumps({
        "schema_version": "amz-runtime-fingerprint/v1",
        "runtime_sha256": runtime, "public_configuration_sha256": configuration,
        "default_trial": (capabilities.get("images") or {}).get("default_trial"),
        "served_scripts_sha256": served_scripts,
        "files": files,
    }, sort_keys=True, indent=2))
    return EXIT_OK


def prerequisites() -> int:
    """只读报告 Linux 运行前提，不启动任何容器/服务：Docker、curl、Playwright/Chromium。"""
    checks: list[dict] = []
    emit(checks, "PR-01", "Docker CLI 可用",
         shutil.which("docker") is not None,
         None if shutil.which("docker") else {"missing_prereq": "docker CLI absent"})
    info = docker("info") if shutil.which("docker") else None
    emit(checks, "PR-02", "Docker daemon 可连接（Linux 容器宿主）",
         info is not None and info.returncode == 0,
         None if (info is not None and info.returncode == 0)
         else {"missing_prereq": "Docker daemon unavailable; needs an approved Linux channel"})
    emit(checks, "PR-03", "curl 可用", shutil.which("curl") is not None,
         None if shutil.which("curl") else {"missing_prereq": "curl absent"})
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415,F401
        emit(checks, "PR-04", "Playwright 可用", True)
    except ImportError:
        emit(checks, "PR-04", "Playwright 可用", False,
             {"missing_prereq": "Playwright absent; run uv sync --locked"})
    failed = [item["id"] for item in checks if not item["ok"]]
    print("结果：{}/{} 通过，{} 失败。".format(
        len(checks) - len(failed), len(checks), len(failed)), flush=True)
    return EXIT_OK if not failed else EXIT_PREREQ


def main() -> int:
    parser = argparse.ArgumentParser(description="Product V2 发布事务探针")
    parser.add_argument("--page-smoke", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--prerequisites", action="store_true",
                        help="只读报告 Linux 运行前提，不启动容器/服务")
    parser.add_argument("--base", default="")
    parser.add_argument("--fingerprint", action="store_true")
    parser.add_argument("--runtime-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    if args.prerequisites:
        return prerequisites()

    if args.fingerprint:
        return runtime_fingerprint(args.runtime_root, args.base or "http://127.0.0.1:8780")
    if args.selftest:
        return selftest()
    if args.page_smoke:
        if not args.base:
            print("missing --base", flush=True)
            return EXIT_PREREQ
        print("=" * 72)
        print("发布验收页面冒烟：{}".format(args.base))
        print("=" * 72)
        checks: list[dict] = []
        ok = page_smoke(args.base, checks)
        failed = [c["id"] for c in checks if not c["ok"]]
        print("结果：{}/{} 通过，{} 失败。".format(
            len(checks) - len(failed), len(checks), len(failed)), flush=True)
        return EXIT_OK if ok else EXIT_FAILED
    print("need --page-smoke --base <url>, --selftest, --fingerprint, or --prerequisites", flush=True)
    return EXIT_PREREQ


if __name__ == "__main__":
    raise SystemExit(main())
