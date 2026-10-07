#!/usr/bin/env python
"""Product V2 发布事务探针：发布验收与事务机制的受控探针。

两种模式（都不读/写任何密钥，不做任何付费调用，不用 BYOK）：

  --page-smoke --base <url>
    对正式入口做真实验收：/api/health、/api/v2/capabilities、静态资源
    （/、styles.css、app.js）的状态/类型/字节，再用已批准的 Playwright
    Chromium 无头 + 隔离临时配置验证实际启动/状态就绪/页面主链
    （安全上下文、WebCrypto、IndexedDB、新建后刷新仍在、零错误）。
    http(s)://127.0.0.1 或 localhost 按安全来源例外验收；
    https 按可信入口验收；其他明文地址按精确负例验收。

  --selftest
    真实调用 deploy/release-transaction.sh：一次性隔离容器/配置/HOME 上的
    脚本 deploy 早失败回退分支（exit 1，事务保持开放，previous 保留）/
    真实开放事务上的过期 finalize 拒绝（exit 4，previous 保留）/
    脏恢复点 deploy 拒绝（exit 1，不删 previous）/
    静态失败 finalize 重验证失败（exit 1，事务保持开放，previous 保留）/
    脚本 rollback 恢复旧服务健康（exit 1，previous 回到 serving 名并健康），
    外加本地真实产品服务器页面验收正反两极。
    初始旧服务基线为一次性 fixture；被测迁移一律走脚本，不复制编排。
    缺 Docker/构建/Playwright 时报 missing_prereq（exit 2），不伪造结果。

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

PROBE_DOCKERFILE = """\
FROM python:3.13-slim-bookworm
WORKDIR /srv
COPY app/server.py app/product_v2_server.py ./app/
COPY app/product_v2/ ./app/product_v2/
COPY src/ ./src/
COPY config/ ./config/
RUN useradd --create-home --uid 10001 appuser \\
    && chown -R appuser:appuser /srv
USER appuser
EXPOSE 8780
HEALTHCHECK --interval=2s --timeout=2s --start-period=3s --retries=30 \\
  CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health', timeout=2)); raise SystemExit(0 if d.get('product') == 'v2' and d.get('server_state') == 'none' else 1)"
CMD ["python", "app/server.py", "--host", "0.0.0.0", "--port", "8780"]
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
    emit(checks, prefix + "-02", "能力查询可用且暴露图像网关端点",
         status == 200 and caps.get("ok") is True and "/api/v2/images/submit" in endpoints,
         {"status": status, "ok": caps.get("ok"),
          "image_provider": ((images or {}).get("provider") or {}).get("provider_id")})

    status, ctype, body = fetch(base, "/")
    html = body.decode("utf-8", "replace")
    emit(checks, prefix + "-03", "首页外壳可达且含项目列表与应用入口标记",
         status == 200 and "text/html" in ctype and 'id="project-list"' in html
         and 'src="./app.js"' in html and len(body) > 0,
         {"status": status, "content_type": ctype, "bytes": len(body),
          "sha256": hashlib.sha256(body).hexdigest()})

    status, ctype, body = fetch(base, "/styles.css")
    emit(checks, prefix + "-04", "样式资源可达、类型正确且非空",
         status == 200 and "text/css" in ctype and len(body) > 0,
         {"status": status, "content_type": ctype, "bytes": len(body),
          "sha256": hashlib.sha256(body).hexdigest()})

    status, ctype, body = fetch(base, "/app.js")
    emit(checks, prefix + "-05", "应用脚本可达、类型正确且非空",
         status == 200 and "javascript" in ctype and len(body) > 0,
         {"status": status, "content_type": ctype, "bytes": len(body),
          "sha256": hashlib.sha256(body).hexdigest()})
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


def docker_image(name: str) -> str:
    result = docker("inspect", "--format", "{{.Config.Image}}", name)
    return result.stdout.strip() if result.returncode == 0 else ""


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
    """真实事务脚本自检：一次性隔离容器/配置/HOME + 真实 deploy/finalize/rollback 调用。

    初始旧服务基线为一次性 fixture（允许）；之后所有被测迁移必须调用仓库的
    deploy/release-transaction.sh，不复制 stop/rename/run/rm 编排。首轮 deploy 用
    无效 Caddy 候选必败走回退；S4c 前换有效反代建开放事务再做静态失败注入，
    不伪造 TLS 结果。测试密钥只活在隔离临时目录，不落日常配置。
    缺 Docker/构建/Playwright 时 exit 2 报 missing_prereq，不伪造结果、不跳过判绿。

    场景语义遵循脚本真实状态机：handled 失败的 deploy/rollback 成功恢复后清事务
    （previous 已回到 serving 名）；open-tx 场景用独立成功 deploy 制造 previous
    保留 + 事务开放，再验过期 finalize 拒绝（exit 4）、静态失败 finalize 重验证
    失败（exit 1）与验收失败 rollback（恢复旧服务健康）；脏点单独构造双容器/无事务。
    页面正反两极用既有 tools/v2_test_server（显式四 fake 接缝的离线手段，
    见该文件头注），只验页面形状与状态就绪，不当作官方模型证据。
    """
    print("=" * 72)
    print("发布事务自检：真实脚本 + 一次性隔离容器/配置")
    print("=" * 72)
    checks: list[dict] = []
    if shutil.which("docker") is None:
        emit(checks, "ST-01", "Docker 可用", False, {"missing_prereq": "no docker CLI"})
        return EXIT_PREREQ
    if docker("info").returncode != 0:
        emit(checks, "ST-01", "Docker 可用", False, {"missing_prereq": "docker info failed"})
        return EXIT_PREREQ
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415,F401
    except ImportError:
        emit(checks, "ST-01", "Playwright 可用", False,
             {"missing_prereq": "playwright not installed; run uv sync --locked"})
        return EXIT_PREREQ
    emit(checks, "ST-01", "Docker 与 Playwright 可用", True)

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    old_tag = "amz-release-probe-old:" + stamp
    new_tag = "amz-release-probe-new:" + stamp
    app = "amz-release-probe-app-" + stamp
    tls = app + "-tls"
    previous = app + "-previous"
    tmp = Path(tempfile.mkdtemp(prefix="release-tx-"))
    # 事务脚本只接受 /tmp/amz-listing-kit-[0-9a-f]* 上下文：隔离目录必须满足该形状。
    context = Path(tempfile.mkdtemp(prefix="amz-listing-kit-", dir="/tmp"))
    fake_home = tmp / "home"
    app_port = 18780
    https_port = 18443

    tracked_containers = [app, previous, tls]
    tracked_images = [old_tag, new_tag]

    def cleanup() -> None:
        for name in tracked_containers:
            if docker_exists(name):
                docker("rm", "--force", name)
        for image in tracked_images:
            docker("rmi", "--force", image)
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(context, ignore_errors=True)

    def read_transaction(env: dict) -> dict:
        path = Path(env["HOME"]) / ".config" / "amz-listing-kit" / "deploy-transaction.env"
        if not path.is_file():
            return {}
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip("'")
        return values

    try:
        # S1：一次性旧/新版本镜像（真实产品树 + 离线 fake 接缝；旧服务基线 fixture，
        # 新镜像仅换标签以区分身份，不改产品内容）。
        build_dir = tmp / "old"
        (build_dir / "app").mkdir(parents=True)
        for name in ("app/server.py", "app/product_v2_server.py"):
            target = build_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        for source in ("app/product_v2", "src", "config"):
            shutil.copytree(ROOT / source, build_dir / source)
        (build_dir / "Dockerfile").write_text(PROBE_DOCKERFILE, encoding="utf-8")
        built = docker("build", "--tag", old_tag, str(build_dir), timeout=600)
        if built.returncode != 0:
            emit(checks, "ST-02", "一次性旧版本镜像真实构建", False,
                 {"missing_prereq": "docker build failed (needs base image pull)",
                  "stderr": built.stderr[-500:]})
            return EXIT_PREREQ
        new_build = docker("build", "--tag", new_tag, str(build_dir), timeout=600)
        if new_build.returncode != 0:
            emit(checks, "ST-02", "一次性新版本镜像真实构建", False,
                 {"missing_prereq": "docker build failed (needs base image pull)",
                  "stderr": new_build.stderr[-500:]})
            return EXIT_PREREQ
        emit(checks, "ST-02", "一次性旧/新版本镜像真实构建", True,
             {"old": old_tag, "new": new_tag})

        # S2：隔离 HOME + 构建上下文（含脚本）。首轮 deploy 用无效 Caddy 候选
        # （反代 127.0.0.1:1）必败走回退；S4c 前换有效反代建开放事务，不伪造 TLS。
        (fake_home / ".config" / "amz-listing-kit" / "tls").mkdir(parents=True, exist_ok=True)
        (context / "deploy").mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "deploy" / "release-transaction.sh",
                    context / "deploy" / "release-transaction.sh")
        caddy_dir = context / "deploy" / "caddy"
        caddy_dir.mkdir(parents=True, exist_ok=True)
        caddy_dir.joinpath("Caddyfile").write_text(
            "https://127.0.0.1:%d {\n\treverse_proxy 127.0.0.1:1\n}\n" % https_port,
            encoding="utf-8")
        script_env = dict(os.environ)
        script_env["HOME"] = str(fake_home)
        old_run = docker("run", "--detach", "--name", app, "--publish",
                         "127.0.0.1:{}:8780".format(app_port), old_tag)
        if old_run.returncode != 0:
            emit(checks, "ST-03", "旧服务基线启动", False, {"stderr": old_run.stderr[-500:]})
            return EXIT_FAILED
        if not wait_healthy(app):
            emit(checks, "ST-03", "旧服务基线健康", False, {"container": app})
            return EXIT_FAILED
        old_image = docker_image(app)
        emit(checks, "ST-03", "旧服务基线健康", True, {"image": old_image})

        deploy_args = [old_tag, app, str(app_port), str(context), "127.0.0.1", str(https_port)]
        good_args = [new_tag, app, str(app_port), str(context), "127.0.0.1", str(https_port)]
        # S3：先用一次性无效 Caddy（反代 127.0.0.1:1）跑脚本 deploy：真实 TLS/HTTPS
        # 失败必须走回退分支（exit 1），旧应用按基线保留且恢复健康，事务保持开放。
        first = run_script("deploy", *deploy_args, env=script_env)
        tx = read_transaction(script_env)
        emit(checks, "ST-04", "早失败走脚本回退分支（exit 1）且事务保持开放",
             first.returncode == 1 and tx.get("IMAGE") == old_tag
             and tx.get("PHASE") in ("baseline", "parked", "new_healthy", "tls_converged",
                                     "tls_backed_up", "tls_installed_new",
                                     "tls_install_intent", "https_ok"),
             {"rc": first.returncode, "phase": tx.get("PHASE"), "image": tx.get("IMAGE"),
              "stderr": first.stderr[-500:]})
        if first.returncode != 1:
            return EXIT_FAILED

        # S4：真实开放事务上的过期 finalize 必须被拒绝（exit 4），previous 保留。
        stale = run_script("finalize", old_tag + "-stale", app, str(app_port), str(context),
                           "127.0.0.1", str(https_port), env=script_env)
        emit(checks, "ST-05", "真实开放事务上的过期 finalize 被拒绝且 previous 保留",
             stale.returncode == 4 and docker_exists(previous)
             and docker_image(previous) == old_image,
             {"rc": stale.returncode, "previous_image": docker_image(previous)})
        if stale.returncode != 4:
            return EXIT_FAILED
        # S4b：脏恢复点（serving 与 previous 并存、无开放事务）的新 deploy 必须
        # 直接拒绝（exit 1），不自动删除 previous。先清事务再试：脚本应拒绝，
        # 且两个容器都原样保留；随后恢复开放事务供 S5 rollback。
        tx_path = Path(script_env["HOME"]) / ".config" / "amz-listing-kit" / "deploy-transaction.env"
        saved_tx = tx_path.read_bytes() if tx_path.is_file() else None
        tx_path.unlink(missing_ok=True)
        dirty = run_script("deploy", *deploy_args, env=script_env)
        dirty_ok = (dirty.returncode == 1 and docker_exists(app) and docker_exists(previous)
                    and not tx_path.is_file())
        emit(checks, "ST-05b", "脏恢复点 deploy 拒绝且不删 previous",
             dirty_ok, {"rc": dirty.returncode, "stderr": dirty.stderr[-500:]})
        if saved_tx is not None:
            tx_path.write_bytes(saved_tx)
        if not dirty_ok:
            return EXIT_FAILED

        # S4c：post-container-healthy 静态失败必须实际回退。用 finalize 重验证
        # 注入：先成功 deploy 建开放事务，再换坏静态候选跑 finalize（identity
        # 仍是开放事务的新镜像，只换 Caddy 反代指向坏静态端口），必须 exit 1。
        # S4c 保持开放事务供 S5 rollback，不清事务。
        caddy_dir.joinpath("Caddyfile").write_text(
            "https://127.0.0.1:%d {\n\treverse_proxy 127.0.0.1:%d\n}\n" % (https_port, app_port),
            encoding="utf-8")
        open_tx = run_script("deploy", *good_args, env=script_env)
        open_ok = (open_tx.returncode == 0 and docker_exists(previous)
                   and docker_image(previous) == old_image)
        emit(checks, "ST-05c-open", "静态失败前重建开放事务且 previous 保留",
             open_ok, {"rc": open_tx.returncode, "previous_image": docker_image(previous),
                       "stderr": open_tx.stderr[-500:]})
        if not open_ok:
            return EXIT_FAILED
        bad_tag = "amz-release-probe-badstatic:" + stamp
        tracked_images.append(bad_tag)
        bad_static = app + "-badstatic"
        tracked_containers.append(bad_static)
        bad_port = 18781
        bad_dir = tmp / "badstatic"
        shutil.copytree(build_dir, bad_dir)
        bad_index = bad_dir / "app" / "product_v2" / "index.html"
        html = bad_index.read_text(encoding="utf-8")
        bad_index.write_text(html.replace('id="project-list"', 'id="project-list-broken"'),
                             encoding="utf-8")
        bad_built = docker("build", "--tag", bad_tag, str(bad_dir), timeout=600)
        if bad_built.returncode != 0:
            emit(checks, "ST-05c", "一次性坏静态镜像真实构建", False,
                 {"missing_prereq": "docker build failed (needs base image pull)",
                  "stderr": bad_built.stderr[-500:]})
            return EXIT_PREREQ
        bad_run = docker("run", "--detach", "--name", bad_static, "--publish",
                         "127.0.0.1:{}:8780".format(bad_port), bad_tag)
        if bad_run.returncode != 0:
            emit(checks, "ST-05c", "一次性坏静态服务启动", False,
                 {"stderr": bad_run.stderr[-500:]})
            return EXIT_FAILED
        if not wait_healthy(bad_static):
            emit(checks, "ST-05c", "一次性坏静态服务健康", False, {"container": bad_static})
            return EXIT_FAILED
        caddy_dir.joinpath("Caddyfile").write_text(
            "https://127.0.0.1:%d {\n\treverse_proxy 127.0.0.1:%d\n}\n" % (https_port, bad_port),
            encoding="utf-8")
        bad = run_script("finalize", *good_args, env=script_env)
        bad_tx = read_transaction(script_env)
        bad_ok = (bad.returncode == 1 and bad_tx.get("IMAGE") == new_tag
                  and docker_exists(previous) and docker_image(previous) == old_image)
        emit(checks, "ST-05c", "静态失败 finalize 重验证失败且 previous 保留",
             bad_ok, {"rc": bad.returncode, "phase": bad_tx.get("PHASE"),
                      "previous_image": docker_image(previous),
                      "stderr": bad.stderr[-500:]})
        if not bad_ok:
            return EXIT_FAILED

        # S5：注入验收后失败 → 脚本 rollback → 旧服务实际恢复健康。
        # S4c 未动开放事务（仍是 good_args 身份），直接用它回退。
        rolled = run_script("rollback", *good_args, "acceptance_failed", env=script_env)
        restored = (rolled.returncode == 1 and docker_exists(app)
                    and docker_image(app) == old_image and wait_healthy(app))
        emit(checks, "ST-06", "脚本 rollback 后旧服务实际恢复健康",
             restored, {"rc": rolled.returncode, "image": docker_image(app),
                        "stderr": rolled.stderr[-500:]})
        if not restored:
            return EXIT_FAILED

        # S6：页面验收正反两极（本地真实产品服务器 green、不可达 red）。
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
        emit(checks, "ST-07", "页面验收对不可达入口判红（非空洞检查）",
             not dead_ok, {"failed_checks": [c["id"] for c in dead_checks if not c["ok"]]})
        emit(checks, "ST-08", "页面验收对真实本地产品服务器判绿",
             live_ok, None)
    finally:
        cleanup()
    failed = [c["id"] for c in checks if not c["ok"]]
    print("结果：{}/{} 通过，{} 失败。".format(
        len(checks) - len(failed), len(checks), len(failed)), flush=True)
    return EXIT_OK if not failed else EXIT_FAILED


def main() -> int:
    parser = argparse.ArgumentParser(description="Product V2 发布事务探针")
    parser.add_argument("--page-smoke", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--base", default="")
    args = parser.parse_args()

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
    print("need --page-smoke --base <url> or --selftest", flush=True)
    return EXIT_PREREQ


if __name__ == "__main__":
    raise SystemExit(main())
