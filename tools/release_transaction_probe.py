#!/usr/bin/env python
"""Product V2 发布事务探针：发布验收与事务机制的受控探针。

  --offline-rollback
    无 Docker 本机可跑的离线证据位：真实执行 deploy/release-transaction.sh 的
    纯文本路径（--help/用法错误 exit 2、无开放事务 finalize/rollback 的精确
    退出码与“不触碰任何服务”后置），再用最小仿真执行器复刻脚本的事务状态机
    （stage fake docker/curl/python3 在 PATH 前缀注入，真实 bash 跑脚本的
    deploy→finalize-late-failure→rollback 全链），证明失败路径回退到上一个
    已知良好状态且 prev/current 两版本 image 指纹确实不同（fake 亦为不同
    sha256 内容对象，不用同一 image 换 tag 充数）。仿真对象只覆盖进程边界
    的 docker/curl/sleep 行为，不复制脚本内部编排；断言全部走真实脚本输出
    与持久化事务文件/备份文件/服务目录快照。缺 bash 时报 missing_prereq
    （exit 2）。本模式 green 只证明事务状态机在失败路径上的回退语义成立，
    不替代 --selftest 的真实容器/TLS/HTTPS 证据（Linux 获批环境仍须跑）。


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
  --offline-rollback 自检缺 bash 时报 missing_prereq（exit 2）。

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


def _bash_path(path: Path | str) -> str:
    """Windows 路径转当前 bash 挂载形态（E:\\x → /mnt/e/x）；已是 POSIX 则原样返回。"""
    text = str(path).replace("\\", "/")
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        return "/mnt/" + text[0].lower() + text[2:]
    return text

def offline_rollback() -> int:
    """无 Docker 本机可跑的离线回退证据位：真实脚本 + 最小仿真执行器。

    第一阶段（OR-01/OR-02）：真实 bash 执行仓库 deploy/release-transaction.sh 的
    纯文本路径——无参用法错误（exit 2）、无开放事务 finalize/rollback 的精确退出码
    （exit 4）与“不触碰任何服务”后置；不注入任何仿真。
    第二阶段（OR-03 起）：在 PATH 前缀注入最小 stage 执行器（fake docker /
    curl / sleep / python3），真实 bash 跑脚本的 deploy → finalize 晚期失败
    （exit 1，previous/journal/备份保留）→ rollback（exit 1）→ 回退后状态核对
    全链；随后按失败类别逐个走一遍：验收/指纹类失败 → rollback 恢复旧版本；
    deploy 阶段失败（候选不健康）→ 脚本自身回退；清理失败 → exit 4（新版本继续
    服务、previous 保留、不自动回退，清障后再 finalize 才收口）；回退本身失败 →
    exit 3 且 journal 保留。回滚真值表由这些**行为**（真实脚本退出码 + 持久化事务
    状态）证明，不再扫描工作流自身文本。fake 只复刻进程边界行为（容器名集合、
    inspect/health 字段、Caddyfile 字节、HTTPS/静态判据），不复制脚本内部编排；
    断言全部走真实脚本 stdout/stderr、退出码与持久化事务文件/备份/Caddyfile/服务快照。
    两版本 image 为不同 sha256 内容对象（tag 名不同且 inspect .Image 不同），不用同一 image 换 tag 充数。
    本模式 green 只证明事务状态机在失败路径上的回退语义成立，不替代 --selftest
    的真实容器/TLS/HTTPS 证据（Linux 获批环境仍须跑）。
    """
    print("=" * 72)
    print("发布事务离线回退证据：真实脚本 + 最小仿真执行器")
    print("=" * 72)
    checks: list[dict] = []
    if shutil.which("bash") is None:
        emit(checks, "OR-00", "bash 可用", False, {"missing_prereq": "bash absent"})
        return EXIT_PREREQ
    emit(checks, "OR-00", "bash 可用", True)

    script = ROOT / "deploy" / "release-transaction.sh"

    def plain(*argv: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", _bash_path(script), *argv],
                              capture_output=True, text=True, timeout=timeout)

    # OR-01：无参进 main → usage（exit 2），不写事务、不碰服务。
    no_args = plain(timeout=60)
    emit(checks, "OR-01", "真实脚本无参返回用法错误 exit 2",
         no_args.returncode == 2 and "release-transaction.sh deploy" in (no_args.stderr or ""),
         {"rc": no_args.returncode, "stderr_tail": (no_args.stderr or "")[-500:]})
    if no_args.returncode != 2:
        return EXIT_FAILED

    # OR-02：隔离 HOME 下无开放事务 finalize/rollback → exit 4（收尾失败，需人工核对），
    # 且脚本不创建任何事务文件（“不触碰服务”后置在无 daemon 本机上退化为 HOME 零副作用）。
    tmp_probe = Path(tempfile.mkdtemp(prefix="release-tx-probe-"))
    fake_home_probe = tmp_probe / "home"
    probe_env = dict(os.environ, HOME=str(fake_home_probe))
    probe_env.pop("RELEASE_DIR", None)
    ctx_probe = "/tmp/amz-listing-kit-%s" % "0" * 8
    fin_empty = subprocess.run(
        ["bash", _bash_path(script), "finalize", "img:tag", "app", "18780", ctx_probe,
         "127.0.0.1", "18443"],
        capture_output=True, text=True, timeout=60, env=probe_env)
    rb_empty = subprocess.run(
        ["bash", _bash_path(script), "rollback", "img:tag", "app", "18780", ctx_probe,
         "127.0.0.1", "18443", "acceptance_failed"],
        capture_output=True, text=True, timeout=60, env=probe_env)
    tx_path_probe = fake_home_probe / ".config" / "amz-listing-kit" / "deploy-transaction.env"
    emit(checks, "OR-02", "无开放事务 finalize/rollback 均 exit 4 且 HOME 零副作用",
         fin_empty.returncode == 4 and rb_empty.returncode == 4 and not tx_path_probe.is_file(),
         {"finalize_rc": fin_empty.returncode, "rollback_rc": rb_empty.returncode,
          "transaction_exists": tx_path_probe.is_file(),
          "finalize_stderr": (fin_empty.stderr or "")[-500:],
          "rollback_stderr": (rb_empty.stderr or "")[-500:]})
    shutil.rmtree(tmp_probe, ignore_errors=True)
    if fin_empty.returncode != 4 or rb_empty.returncode != 4:
        return EXIT_FAILED

    # OR-03 起：最小仿真执行器。WSL 侧对 Windows 盘符 /mnt/e 挂载 exec 受限，
    # stage/state/HOME/context 全放 WSL 原生 /tmp；脚本/Caddyfile 读穿 /mnt/e 即可。
    # stage 目录只提供进程边界行为；真实 bash 跑真实脚本。
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    old_tag = "amz-release-offline-old:" + stamp
    new_tag = "amz-release-offline-new:" + stamp
    app = "amz-release-offline-app-" + stamp
    previous = app + "-previous"
    tls = app + "-tls"
    app_port, https_port = 18780, 18443
    # 两版本 image：不同 sha256 内容对象（tag 不同且 inspect .Image 不同）。
    old_digest = "sha256:" + hashlib.sha256(("offline-old-image-" + stamp).encode()).hexdigest()
    new_digest = "sha256:" + hashlib.sha256(("offline-new-image-" + stamp).encode()).hexdigest()
    marker_a = "release-marker-a-" + stamp
    marker_b = "release-marker-b-" + stamp

    def sh(cmd: str, timeout: int = 30) -> str:
        # 经 Windows bash.exe → WSL 两层转义：命令中避免 $ 变量，全部用绝对路径与固定串。
        result = subprocess.run(["bash", "-c", cmd],
                                capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError("stage setup failed: " + (result.stderr or "")[-500:])
        return result.stdout.strip()

    sh("mktemp -d /tmp/release-tx-offline.XXXXXXXX > /tmp/release-tx-offline.root")
    wsl_root = sh("cat /tmp/release-tx-offline.root")
    wsl_stage, wsl_state, wsl_home = (wsl_root + "/stage", wsl_root + "/state", wsl_root + "/home")
    sh("mkdir -p '" + wsl_stage + "' '" + wsl_state + "' '" + wsl_home + "/.config/amz-listing-kit/tls'")
    live_caddy_posix = wsl_home + "/.config/amz-listing-kit/tls/Caddyfile"
    transaction_posix = wsl_home + "/.config/amz-listing-kit/deploy-transaction.env"
    backup_posix = wsl_home + "/.config/amz-listing-kit/tls/Caddyfile.release-backup"
    marker_posix = wsl_state + "/served_marker.txt"
    mode_posix = wsl_state + "/https_mode.txt"
    sh("mktemp -d /tmp/amz-listing-kit-0abcdef.XXXXXX > /tmp/release-tx-old.ctx")
    sh("mktemp -d /tmp/amz-listing-kit-0abcdef.XXXXXX > /tmp/release-tx-new.ctx")
    old_context = sh("cat /tmp/release-tx-old.ctx")
    new_context = sh("cat /tmp/release-tx-new.ctx")
    contexts = [old_context, new_context]
    # 最小构建上下文：脚本只读 context/deploy/release-transaction.sh（安装自用）
    # 与 context/deploy/caddy/Caddyfile（TLS 收敛）；docker build 由 stage 仿真。
    script_posix = _bash_path(script)
    for context in contexts:
        sh("mkdir -p '%s/deploy/caddy'; cp '%s' '%s/deploy/release-transaction.sh'; printf 'x' > /dev/null"
           % (context, script_posix, context))
    sh("printf '%s\\n' '%s' > '%s/served_marker.txt'; printf ok > '%s/https_mode.txt'; printf '%s\\n' '%s' > '%s/content_old.txt'; printf '%s\\n' '%s' > '%s/content_new.txt'"
       % (marker_a, marker_a, wsl_state, wsl_state, marker_a, marker_a, wsl_state, marker_b, marker_b, wsl_state))
    old_config = ("https://127.0.0.1:%d {\n\ttls internal\n%s}\n" % (https_port, "\t# old-config\n"))
    sh("cat > '%s' <<'OLDCFG'\n%sOLDCFG" % (live_caddy_posix, old_config))
    sh("printf '" + old_tag + "' > '" + wsl_state + "/container_" + app + ".image'")
    sh("printf 'caddy:2' > '" + wsl_state + "/container_" + tls + ".image'")

    def write_stage(name: str, body: str) -> None:
        # 经 Windows bash.exe 传 heredoc 会被外层吃掉 $：改经 WSL 文件中转写 stage 脚本。
        tmp_local = Path(tempfile.mkdtemp(prefix="stage-write-")) / name
        tmp_local.write_text(body.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        wsl_tmp = sh("mktemp /tmp/stage-write.XXXXXX")
        sh("cat '" + _bash_path(tmp_local) + "' > '" + wsl_tmp + "'")
        sh("cp '" + wsl_tmp + "' '" + wsl_stage + "/" + name + "'")
        sh("chmod 755 '" + wsl_stage + "/" + name + "'")
        sh("rm -f '" + wsl_tmp + "'")
        shutil.rmtree(tmp_local.parent, ignore_errors=True)

    write_stage("docker", """#!/usr/bin/env bash
# 最小 stage docker：只复刻容器名集合/inspect 字段/health/Caddy 字节语义。
# 不复制 deploy/release-transaction.sh 的任何编排（park/rename/restore/cleanup 全由真实脚本执行）。
set -uo pipefail
STATE_DIR="${RELEASE_TX_STATE:?missing state}"
log_call() { printf '%s\n' "docker $*" >> "${STATE_DIR}/docker_calls.log"; }
log_call "$@"
cmd="${1:-}"; shift || true
image_of() { cat "${STATE_DIR}/container_$1.image" 2>/dev/null || true; }
health_of() {
  # 可按镜像注入 unhealthy：只让本次候选镜像不健康，上一版本仍判健康，
  # 用于“deploy 阶段失败 → 脚本自身回退”的故障注入，不改变健康判据本身。
  local img bad
  img="$(image_of "$1")"
  bad="$(cat "${STATE_DIR}/bad_health_image.txt" 2>/dev/null || true)"
  if [ -n "$bad" ] && [ "$img" = "$bad" ]; then printf 'unhealthy'; else printf 'healthy'; fi
}
mode_is() { [ "$(cat "${STATE_DIR}/$1.txt" 2>/dev/null || true)" = "fail" ]; }
case "$cmd" in
  container)
    sub="${1:-}"; name="${2:-}"
    if [ "$sub" = "inspect" ] && [ -f "${STATE_DIR}/container_${name}.image" ]; then exit 0; fi
    exit 1;;
  inspect)
    format=""; ref=""
    while [ "$#" -gt 0 ]; do case "$1" in --format) format="$2"; shift 2;; *) ref="$1"; shift;; esac; done
    name="$(basename "$ref")"
    case "$format" in
      '{{.Config.Image}}') image_of "$name" || exit 1;;
      '{{.Image}}') image_of "$name" || exit 1;;
      '{{.State.Running}}') [ -f "${STATE_DIR}/container_${name}.image" ] && printf 'true' || exit 1;;
      '{{.State.Health.Status}}') [ -f "${STATE_DIR}/container_${name}.image" ] && health_of "$name" || exit 1;;
      *) exit 1;;
    esac
    exit 0;;
  images)
    ref="${@: -1}"
    case "$ref" in
      "${RELEASE_TX_OLD_TAG:?}") printf '${RELEASE_TX_OLD_DIGEST:?}' | sed 's/^sha256://';;
      "${RELEASE_TX_NEW_TAG:?}") printf '${RELEASE_TX_NEW_DIGEST:?}' | sed 's/^sha256://';;
      *) printf '${RELEASE_TX_OLD_DIGEST:?}' | sed 's/^sha256://';;
    esac
    exit 0;;
  ps) printf 'stage ps (no real engine)\\n'; exit 0;;
  build) exit 0;;
  run)
    name=""; image=""
    while [ "$#" -gt 0 ]; do case "$1" in --name) name="$2"; shift 2;; --volume) shift 2;; --publish|--network|--restart|--env-file) shift; [ "$#" -gt 0 ] && shift;; --detach|--rm|-i|-t) shift;; -*) shift;; *) image="$1"; shift;; esac; done
    printf '%s' "$image" > "${STATE_DIR}/container_${name}.image"
    exit 0;;
  stop|start|restart)
    # start_mode=fail：旧版本起不来 → 回退本身失败（exit 3），journal 必须保留。
    if [ "$cmd" = "start" ] && mode_is start_mode; then exit 1; fi
    exit 0;;
  rename)
    src="$1"; dst="$2"
    mv "${STATE_DIR}/container_${src}.image" "${STATE_DIR}/container_${dst}.image" 2>/dev/null || exit 1
    exit 0;;
  rm)
    # rm_mode=fail：验收通过后清理 previous 失败 → finalize exit 4，绝不自动回滚。
    if mode_is rm_mode; then printf 'stage rm refused\n' >&2; exit 1; fi
    while [ "$#" -gt 0 ]; do case "$1" in --force|-f) shift;; *) rm -f "${STATE_DIR}/container_$(basename "$1").image"; shift;; esac; done
    exit 0;;
  cp|rmi|volume|logs) exit 0;;
  *) exit 1;;
esac
""".replace("${RELEASE_TX_OLD_TAG:?}", old_tag
           ).replace("${RELEASE_TX_NEW_TAG:?}", new_tag
                     ).replace("${RELEASE_TX_OLD_DIGEST:?}", old_digest
                               ).replace("${RELEASE_TX_NEW_DIGEST:?}", new_digest))
    write_stage("curl", """#!/usr/bin/env bash
# 最小 stage curl：-f 成功即 exit 0；body 按 URL 影射到 stage 文件（health/marker/静态）。
# https_mode=broken_static 时静态入口返回 404，使 finalize 晚期失败但 health 仍绿。
set -uo pipefail
STATE_DIR="${RELEASE_TX_STATE:?missing state}"
url=""; out=""
while [ "$#" -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; --max-time) shift 2;; -*) shift;; *) url="$1"; shift;; esac; done
path="${url#*://*/}"; path="/${path%%\\?*}"
mode="$(cat "${STATE_DIR}/https_mode.txt" 2>/dev/null || printf ok)"
body=""
case "$path" in
  /api/health) body='{"product":"v2","server_state":"none"}';;
  /) body='<html><body><div id="project-list"></div></body></html>';;
  /styles.css) body='body{}'; [ "$mode" = "broken_static" ] && exit 22;;
  /entry.js|/app.js) body='console.log(1)'; [ "$mode" = "broken_static" ] && exit 22;;
  /release-marker.txt) body="$(cat "${STATE_DIR}/served_marker.txt" 2>/dev/null || true)";;
  *) exit 22;;
esac
if [ -n "$out" ]; then printf '%s' "$body" > "$out"; else printf '%s' "$body"; fi
exit 0
""")
    write_stage("sleep", """#!/usr/bin/env bash
# stage sleep：离线自检不真实等待，立即成功（只影响脚本的轮询等待时长，不改变判据）。
exit 0
""")
    write_stage("python3", """#!/usr/bin/env bash
# stage python3：探针本进程仍用真实 python3；stage 仅占位，防脚本误调。
exit 0
""")

    def staged(*argv: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        # Windows bash.exe 会丢弃 PATH 中的 WSL 原生段并吞掉 "$@"：改把 6 个位置参数
        # 逐个拼进内层命令（argv 全部来自本探针固定量，无外部输入）。
        inner = "export HOME='" + wsl_home + "' PATH='" + wsl_stage + ":/usr/local/bin:/usr/bin:/bin' RELEASE_TX_STATE='" + wsl_state + "' CURL_CA_BUNDLE='" + wsl_home + "/probe-ca.crt'; exec bash '" + script_posix + "'"
        for a in argv:
            inner += " '" + a.replace("'", "'\"'\"'") + "'"
        env = dict(os.environ)
        env.pop("RELEASE_DIR", None)
        return subprocess.run(["bash", "-c", inner],
                              capture_output=True, text=True, timeout=timeout, env=env)

    def image_of(name: str) -> str:
        return sh("cat '%s/container_%s.image' 2>/dev/null || true" % (wsl_state, name))

    def tx_text() -> str:
        return sh("cat '%s' 2>/dev/null || true" % transaction_posix)

    def caddy_text() -> str:
        return sh("cat '%s' 2>/dev/null || true" % live_caddy_posix)

    def tx_exists() -> bool:
        return sh("[ -f '%s' ] && printf yes || printf no" % transaction_posix) == "yes"

    def backup_exists() -> bool:
        return sh("[ -f '%s' ] && printf yes || printf no" % backup_posix) == "yes"

    def mode_text() -> str:
        return sh("cat '%s' 2>/dev/null || printf ok" % mode_posix)

    def marker_text() -> str:
        return sh("cat '%s' 2>/dev/null || true" % marker_posix)

    try:
        argv_new = [new_tag, app, str(app_port), new_context, "127.0.0.1", str(https_port)]

        # OR-03：两版本 image 指纹确实不同（tag 名不同 + sha256 不同）。
        ids_differ = (old_tag != new_tag and old_digest != new_digest
                      and old_digest.startswith("sha256:") and new_digest.startswith("sha256:"))
        emit(checks, "OR-03", "两版本 image 指纹确实不同（不用同一 image 换 tag 充数）",
             ids_differ, {"old_tag": old_tag, "new_tag": new_tag,
                          "old_image_id": old_digest, "new_image_id": new_digest})
        if not ids_differ:
            return EXIT_FAILED

        # OR-04：真实 deploy 开放事务并保留旧容器/配置；Caddy 变更触发备份落盘。
        sh("printf '%s' '%s' > '%s'" % (marker_b, marker_b, marker_posix))
        sh("cat > '%s/deploy/caddy/Caddyfile' <<'NEWCFG'\nhttps://127.0.0.1:%d {\n\ttls internal\n\t# new-config\n\treverse_proxy 127.0.0.1:%d\n}\nNEWCFG"
           % (new_context, https_port, app_port))
        deployed = staged("deploy", *argv_new)
        body = tx_text()
        deploy_ok = (deployed.returncode == 0 and image_of(app) == new_tag
                     and image_of(previous) == old_tag
                     and tx_exists() and backup_exists()
                     and ("PREVIOUS_EXISTED='true'" in body)
                     and ("PHASE='https_ok'" in body))
        emit(checks, "OR-04", "真实 deploy 开放事务并保留旧容器/配置（previous 未提前删）",
             deploy_ok,
             {"rc": deployed.returncode, "serving_image": image_of(app),
              "previous_image": image_of(previous), "transaction_exists": tx_exists(),
              "backup_exists": backup_exists(), "stderr_tail": (deployed.stderr or "")[-800:]})
        if not deploy_ok:
            return EXIT_FAILED

        # OR-05：晚期注入坏静态（health 仍绿），finalize 必须判红 exit 1 且保留恢复点。
        sh("printf broken_static > '%s'" % mode_posix)
        failed = staged("finalize", *argv_new)
        failed_ok = (failed.returncode == 1 and image_of(previous) == old_tag
                     and tx_exists() and backup_exists()
                     and caddy_text() != old_config)
        emit(checks, "OR-05", "坏静态 finalize 判红 exit 1 且 previous/journal/备份保留",
             failed_ok,
             {"rc": failed.returncode, "previous_image": image_of(previous),
              "transaction_exists": tx_exists(), "backup_exists": backup_exists(),
              "stderr_tail": (failed.stderr or "")[-800:]})
        if not failed_ok:
            return EXIT_FAILED

        # OR-06：真实 rollback 回到旧版本（serving=old tag）并清除事务/备份；服务字节回 marker A。
        sh("printf ok > '" + mode_posix + "'; printf '" + marker_a + "' > '" + marker_posix + "'")
        rolled = staged("rollback", *argv_new, "acceptance_failed")
        prev_gone = sh("[ -f '%s/container_%s.image' ] && printf yes || printf no"
                       % (wsl_state, previous))
        # install 恢复会吞掉备份末尾换行：按字节语义核对（尾换行归一），不钉死换行差异。
        rolled_ok = (rolled.returncode == 1 and image_of(app) == old_tag
                     and prev_gone == "no"
                     and not tx_exists()
                     and caddy_text().rstrip("\n") == old_config.rstrip("\n")
                     and marker_text() == marker_a)
        # 回退前后服务字节指纹必须不同（B≠A：真回退非原地重启）。
        rolled_ok = rolled_ok and (marker_a.strip() != marker_b.strip())
        emit(checks, "OR-06", "真实 rollback 回到旧 image/marker A 并清除事务（两版本指纹不同）",
             rolled_ok,
             {"rc": rolled.returncode, "serving_image": image_of(app),
              "old_tag": old_tag, "new_tag": new_tag,
              "old_image_id": old_digest, "new_image_id": new_digest,
              "served_marker": marker_text(), "expected_marker": marker_a,
              "prev_gone": prev_gone, "tx_exists": tx_exists(),
              "caddy_match": (caddy_text() == old_config),
              "transaction_exists": tx_exists(),
              "stderr_tail": (rolled.stderr or "")[-800:]})
        if not rolled_ok:
            return EXIT_FAILED

        # OR-07：回退后状态核对——无残留开放事务（stale finalize 拒绝 exit 4）且旧服务/配置完整。
        recheck = staged("finalize", *argv_new)
        recheck_ok = (recheck.returncode == 4 and image_of(app) == old_tag
                      and not tx_exists() and not backup_exists()
                      and caddy_text().rstrip("\n") == old_config.rstrip("\n")
                      and mode_text() == "ok")
        emit(checks, "OR-07", "回退后无开放事务（stale finalize 拒绝 exit 4）且旧服务/配置完整",
             recheck_ok,
             {"rc": recheck.returncode, "serving_image": image_of(app),
              "transaction_exists": tx_exists(),
              "stderr_tail": (recheck.stderr or "")[-800:]})
        if not recheck_ok:
            return EXIT_FAILED

        # OR-08：deploy 成功开放事务后，**验收/运行时指纹类失败**（finalize 之前的失败类别）
        # 必须回退到上一版本；这类失败不回滚就等于让坏版本当着正服务。
        def refresh_context(context: str) -> None:
            # 脚本成功收口会按设计删除构建上下文（deploy 的 EXIT trap / finalize 收尾），
            # 后续场景再部署必须按同一内容重建上下文（脚本只读 context/deploy/... 两项）。
            sh("rm -rf '%s'; mkdir -p '%s/deploy/caddy'; cp '%s' '%s/deploy/release-transaction.sh'"
               % (context, context, script_posix, context))
            sh("cat > '%s/deploy/caddy/Caddyfile' <<'NEWCFG'\n"
               "https://127.0.0.1:%d {\n\ttls internal\n\t# new-config\n\treverse_proxy 127.0.0.1:%d\n}\nNEWCFG"
               % (context, https_port, app_port))

        refresh_context(new_context)
        deployed_accept = staged("deploy", *argv_new)
        accept_rolled = staged("rollback", *argv_new, "acceptance_failed")
        accept_prev_gone = sh("[ -f '%s/container_%s.image' ] && printf yes || printf no"
                              % (wsl_state, previous))
        accept_ok = (deployed_accept.returncode == 0 and accept_rolled.returncode == 1
                     and image_of(app) == old_tag and accept_prev_gone == "no"
                     and not tx_exists() and not backup_exists()
                     and caddy_text().rstrip("\n") == old_config.rstrip("\n")
                     and marker_text() == marker_a)
        emit(checks, "OR-08", "deploy 后验收/指纹类失败 → rollback 恢复旧版本并清事务",
             accept_ok,
             {"deploy_rc": deployed_accept.returncode, "rollback_rc": accept_rolled.returncode,
              "serving_image": image_of(app), "previous_gone": accept_prev_gone,
              "transaction_exists": tx_exists(), "backup_exists": backup_exists(),
              "served_marker": marker_text(),
              "deploy_stderr": (deployed_accept.stderr or "")[-1500:],
              "stderr_tail": (accept_rolled.stderr or "")[-800:]})
        if not accept_ok:
            return EXIT_FAILED

        # OR-09：**deploy 阶段失败**（新容器起不来/不健康）由脚本自身回退，不把失败报成发布成功。
        refresh_context(new_context)
        sh("printf '%s' '%s' > '%s/bad_health_image.txt'" % (new_tag, new_tag, wsl_state))
        deploy_failed = staged("deploy", *argv_new)
        sh("rm -f '%s/bad_health_image.txt'" % wsl_state)
        deploy_fail_prev_gone = sh("[ -f '%s/container_%s.image' ] && printf yes || printf no"
                                   % (wsl_state, previous))
        deploy_fail_ok = (deploy_failed.returncode == 1 and image_of(app) == old_tag
                          and deploy_fail_prev_gone == "no" and not tx_exists()
                          and caddy_text().rstrip("\n") == old_config.rstrip("\n")
                          and marker_text() == marker_a
                          and "new container unhealthy" in (deploy_failed.stderr or ""))
        emit(checks, "OR-09", "deploy 阶段失败（候选不健康）自身回退到旧版本，exit 1 且无残留事务",
             deploy_fail_ok,
             {"rc": deploy_failed.returncode, "serving_image": image_of(app),
              "previous_gone": deploy_fail_prev_gone, "transaction_exists": tx_exists(),
              "served_marker": marker_text(),
              "stderr_tail": (deploy_failed.stderr or "")[-800:]})
        if not deploy_fail_ok:
            return EXIT_FAILED

        # OR-10：**清理失败**（新版本已健康，删 previous 失败）→ exit 4，新版本继续服务、
        # previous 保留、绝不自动回退；清障后再 finalize 才真正收口。
        refresh_context(new_context)
        deployed_clean = staged("deploy", *argv_new)
        sh("printf '%s' '%s' > '%s'" % (marker_b, marker_b, marker_posix))
        sh("printf fail > '%s/rm_mode.txt'" % wsl_state)
        cleanup_failed = staged("finalize", *argv_new)
        sh("rm -f '%s/rm_mode.txt'" % wsl_state)
        prev_kept = image_of(previous)
        cleanup_ok = (deployed_clean.returncode == 0 and cleanup_failed.returncode == 4
                      and image_of(app) == new_tag and prev_kept == old_tag
                      and tx_exists() and marker_text() == marker_b
                      and "finalize_cleanup_failed" in (cleanup_failed.stderr or ""))
        emit(checks, "OR-10", "清理失败 → exit 4：新版本继续服务、previous 保留、不自动回退（人工清理）",
             cleanup_ok,
             {"deploy_rc": deployed_clean.returncode, "finalize_rc": cleanup_failed.returncode,
              "serving_image": image_of(app), "previous_image": prev_kept,
              "transaction_exists": tx_exists(), "served_marker": marker_text(),
              "stderr_tail": (cleanup_failed.stderr or "")[-800:]})
        if not cleanup_ok:
            return EXIT_FAILED
        manual_cleanup = staged("finalize", *argv_new)
        manual_ok = (manual_cleanup.returncode == 0 and image_of(app) == new_tag
                     and not tx_exists() and not backup_exists()
                     and sh("[ -f '%s/container_%s.image' ] && printf yes || printf no"
                            % (wsl_state, previous)) == "no")
        emit(checks, "OR-10b", "清障后同一 finalize 收口：exit 0，previous/备份/事务才被清理",
             manual_ok,
             {"rc": manual_cleanup.returncode, "serving_image": image_of(app),
              "transaction_exists": tx_exists(), "backup_exists": backup_exists(),
              "stderr_tail": (manual_cleanup.stderr or "")[-800:]})
        if not manual_ok:
            return EXIT_FAILED

        # OR-11：**回退本身失败**（旧版本起不来）→ exit 3 且 journal/恢复点保留，
        # 绝不把失败的回退报成已恢复。
        argv_old = [old_tag, app, str(app_port), new_context, "127.0.0.1", str(https_port)]
        refresh_context(new_context)
        staged("deploy", *argv_old)
        sh("printf fail > '%s/start_mode.txt'" % wsl_state)
        unrecovered = staged("rollback", *argv_old, "acceptance_failed")
        sh("rm -f '%s/start_mode.txt'" % wsl_state)
        unrecovered_ok = (unrecovered.returncode == 3 and tx_exists()
                          and "unrecovered_failed_release" in (unrecovered.stderr or ""))
        emit(checks, "OR-11", "回退失败（旧版本起不来）→ exit 3 且 journal 保留，不报成已恢复",
             unrecovered_ok,
             {"rc": unrecovered.returncode, "transaction_exists": tx_exists(),
              "stderr_tail": (unrecovered.stderr or "")[-800:]})
        if not unrecovered_ok:
            return EXIT_FAILED
    finally:
        sh("rm -rf '%s' '%s' '%s'" % (wsl_root, old_context, new_context))
    failed_checks = [item["id"] for item in checks if not item["ok"]]
    print("结果：%d/%d 通过，%d 失败。" %
          (len(checks) - len(failed_checks), len(checks), len(failed_checks)), flush=True)
    return EXIT_FAILED if failed_checks else EXIT_OK

def main() -> int:
    parser = argparse.ArgumentParser(description="Product V2 发布事务探针")
    parser.add_argument("--page-smoke", action="store_true")
    parser.add_argument("--offline-rollback", action="store_true",
                        help="无 Docker 本机可跑的离线回退证据位（真实脚本 + 最小仿真执行器）")
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
    if args.offline_rollback:
        return offline_rollback()
    print("need --page-smoke --base <url>, --selftest, --offline-rollback, --fingerprint, or --prerequisites", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
