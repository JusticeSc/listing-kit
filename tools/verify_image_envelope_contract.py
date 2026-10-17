"""P6/SEL-025：归一化图像信封的跨语言等价矩阵（真实响应 + 结构变异）。

断言的是**同一批字节在两个真实消费者上的判定完全相同**：

  - Python 权威：``src/providers/v2_image.py`` 的 ``ImageWireEnvelope``（结构权威模型）；
  - 浏览器权威：构建期从该模型导出 JSON Schema、再用 Ajv standalone 生成的校验器
    ``app/product_v2/domain/generated/image-task-envelope.validate.js``。

案例来源是真实响应：本工具用真实 ``ProductV2Server`` + 假 provider 走
``/api/v2/images/submit`` 与 ``/api/v2/images/status``，取回真实响应体（异步成功、
同步协议带字节、input_rejected、provider_unknown 四类形状），再在真实字节上做结构
变异（缺字段、多字段、类型错、词表外、越界）。所以断言对象是「实际收到的信封」，
不是手抄的形状，也不做任何源码文本/接线断言。

判红的情形：
  1) 任一变异两侧判定不同；
  2) 任一 must_reject 变异被任一侧放行；
  3) 任一真实响应被任一侧拒绝（生产者输出必须先过自己的消费者）；
  4) 生成物与当前模型不同步（重跑 codegen 会写出别的字节）或缺 export/含 require。

刻意排除的边界（不是漏测）：JSON 里的 ``1e2``/``1.0`` 在 JS 里就是整数 100/1，而 Python
严格模式下是 float；该差异来自 JSON 解析层，任何 JS 校验器都无法表达。真实生产者只发
int，这里不伪造这种案例。

运行：
    uv run --locked python tools/verify_image_envelope_contract.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from app.product_v2_server import (IMAGE_STATUS_PATH, IMAGE_SUBMIT_PATH,
                                   create_product_v2_server)  # noqa: E402
from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_image import ImageTaskResult, ImageWireEnvelope  # noqa: E402

GENERATED = Path("app/product_v2/domain/generated")
SCHEMA_NAME = "image-task-envelope.schema.json"
VALIDATOR_NAME = "image-task-envelope.validate.js"
EXPORT_NAME = "validateImageEnvelope"
EXPORT_SCHEMA_TOOL = "tools/export_image_envelope_schema.py"
GENERATE_VALIDATOR_TOOL = "tools/generate_image_envelope_validator.mjs"
PARITY_TOOL = "tools/check_image_envelope_parity.mjs"

ACTION_ID = "act-11111111-2222-3333-4444-555555555555"
REFERENCE_SIZE = 512
PROMPT = "白色陶瓷马克杯，白底商品图，正面平视。"

problems: list[str] = []
checks: list[tuple[str, bool, dict[str, Any]]] = []


def check(name: str, ok: bool, detail: dict[str, Any] | None = None) -> None:
    checks.append((name, bool(ok), detail or {}))
    if not ok:
        problems.append(name)


# ------------------------------------------------------------------ 服务端：真实响应


class SyncImageProvider(FakeImageProvider):
    """同步协议形状（V2.R5.2）：提交一步给终态，结果字节随同一次响应回浏览器。"""

    def submit(self, request: Any) -> ImageTaskResult:
        self.calls["submit"] += 1
        return ImageTaskResult(
            provider_id=self.provider_id, model_id=self.model_id, task_id=None,
            status="SUCCEEDED", result_count=1, request_id="req-sync-0001",
            sync_result=(self.bytes_for("sync-envelope", self.size), "image/png"))


def reference_block() -> dict[str, Any]:
    content = FakeImageProvider.bytes_for("envelope-reference", REFERENCE_SIZE)
    return {"role": "primary", "media_type": "image/png",
            "sha256": hashlib.sha256(content).hexdigest(),
            "data_base64": base64.b64encode(content).decode("ascii")}


def submit_body() -> dict[str, Any]:
    return {"action_id": ACTION_ID, "prompt": PROMPT, "references": [reference_block()],
            "size": "1344*1344"}


def post(base: str, path: str, payload: Any) -> tuple[int, Any]:
    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def real_responses() -> list[tuple[str, Any]]:
    """真实响应体；返回 (名字, 解析后的 JSON)。mode 表按请求切换替身场景。"""

    mode: dict[str, str] = {"scenario": "ok"}

    def image_factory() -> FakeImageProvider:
        scenario = mode["scenario"]
        if scenario == "sync":
            return SyncImageProvider(scenario="ok", size=REFERENCE_SIZE)
        return FakeImageProvider(scenario=scenario, size=REFERENCE_SIZE)

    server = create_product_v2_server("127.0.0.1", 0, image_provider_factory=image_factory)
    server.start()
    base = server.base_url
    cases: list[tuple[str, Any]] = []
    try:
        mode["scenario"] = "ok"
        status, async_submit = post(base, IMAGE_SUBMIT_PATH, submit_body())
        cases.append((f"real-async-submit-{status}", async_submit))
        task_id = (async_submit.get("task") or {}).get("task_id")
        status, async_status = post(base, IMAGE_STATUS_PATH, {"task_id": task_id})
        cases.append((f"real-async-status-{status}", async_status))

        mode["scenario"] = "sync"
        status, sync_submit = post(base, IMAGE_SUBMIT_PATH, submit_body())
        cases.append((f"real-sync-submit-{status}", sync_submit))

        # input_rejected：真实路由用契约校验挡下（action_id 不合法），不调用任何 provider。
        status, rejected = post(base, IMAGE_SUBMIT_PATH, {**submit_body(), "action_id": "short"})
        cases.append((f"real-input-rejected-{status}", rejected))

        mode["scenario"] = "submit_unknown"
        status, unknown = post(base, IMAGE_SUBMIT_PATH, submit_body())
        cases.append((f"real-provider-unknown-{status}", unknown))

        mode["scenario"] = "failed"
        status, failed = post(base, IMAGE_SUBMIT_PATH, submit_body())
        cases.append((f"real-provider-failed-{status}", failed))

        mode["scenario"] = "status_unknown"
        status, status_unknown = post(base, IMAGE_STATUS_PATH, {"task_id": task_id})
        cases.append((f"real-status-unknown-{status}", status_unknown))
    finally:
        server.stop()
    return cases


# ------------------------------------------------------------------ 变异


def mutations(name: str, value: Any) -> list[tuple[str, Any, bool]]:
    """在真实字节上做结构变异；第三项 True 表示两侧都必须拒绝。"""

    out: list[tuple[str, Any, bool]] = []

    def add(suffix: str, mutated: Any, must_reject: bool = True) -> None:
        out.append((f"{name}::{suffix}", mutated, must_reject))

    add("null", None)
    add("array", [value])
    add("number", 0)
    add("json-string", json.dumps(value))
    if not isinstance(value, dict):
        return out

    add("no-ok", {key: item for key, item in value.items() if key != "ok"})
    add("ok-string", {**value, "ok": "true"})
    add("ok-null", {**value, "ok": None})
    add("unknown-string", {**value, "unknown": "false"})
    add("extra-envelope-key", {**value, "workspace": "/tmp/x"})
    # 缺可选键必须继续被接受：这是旧消费者的既有接受集，收紧它等于把可读信封变成 Unknown。
    add("no-unknown-key", {key: item for key, item in value.items() if key != "unknown"}, False)

    task = value.get("task")
    if isinstance(task, dict):
        add("no-task", {key: item for key, item in value.items() if key != "task"})
        add("no-task-provider", {**value, "task": {k: v for k, v in task.items() if k != "provider"}})
        add("no-task-id", {**value, "task": {k: v for k, v in task.items() if k != "task_id"}})
        add("no-status", {**value, "task": {k: v for k, v in task.items() if k != "status"}})
        add("no-request-id-key", {**value, "task": {k: v for k, v in task.items() if k != "request_id"}}, False)
        add("no-sync-key", {**value, "task": {k: v for k, v in task.items() if k != "sync"}}, False)
        add("task-extra-key", {**value, "task": {**task, "extra": 1}})
        add("task-null", {**value, "task": None})
        add("provider-string", {**value, "task": {**task, "provider": "dashscope-qwen-image"}})
        add("provider-extra-key",
            {**value, "task": {**task, "provider": {**task["provider"], "region": "cn"}}})
        add("provider-bad-identifier",
            {**value, "task": {**task, "provider": {**task["provider"], "provider_id": "bad id!"}}})
        add("provider-missing-model",
            {**value, "task": {**task, "provider": {"provider_id": task["provider"]["provider_id"]}}})
        add("task-id-number", {**value, "task": {**task, "task_id": 5}})
        add("task-id-empty-string", {**value, "task": {**task, "task_id": ""}}, False)
        add("status-off-vocabulary", {**value, "task": {**task, "status": "ok"}})
        add("status-lowercase", {**value, "task": {**task, "status": "running"}})
        add("status-type-number", {**value, "task": {**task, "status": 3}})
        add("count-string", {**value, "task": {**task, "result_count": "1"}})
        add("count-negative", {**value, "task": {**task, "result_count": -1}})
        add("count-float", {**value, "task": {**task, "result_count": 1.5}})
        add("sync-string", {**value, "task": {**task, "sync": "true"}})
        add("unknown-task-number", {**value, "task": {**task, "unknown": 0}})

    error = value.get("error")
    if isinstance(error, dict):
        add("no-error-block", {key: item for key, item in value.items() if key != "error"})
        add("no-error-message", {**value, "error": {k: v for k, v in error.items() if k != "message"}})
        add("error-extra-key", {**value, "error": {**error, "hint": "x"}})
        add("error-family-off-vocabulary", {**value, "error": {**error, "family": "boom"}})
        add("error-retry-off-vocabulary", {**value, "error": {**error, "retry_policy": "later"}})
        add("error-string", {**value, "error": "boom"})
        add("error-code-number", {**value, "error": {**error, "code": 7}})
        add("error-no-details-key",
            {**value, "error": {k: v for k, v in error.items() if k != "details"}}, False)
    elif "error" not in value:
        add("error-block-added",
            {**value, "error": {"family": "internal", "code": "INTERNAL_ERROR",
                                "message": "服务器内部错误。", "retry_policy": "fatal"}})

    sha = value.get("image_sha256")
    if isinstance(sha, str):
        add("sha-truncated", {**value, "image_sha256": sha[:-1]})
        add("sha-uppercase", {**value, "image_sha256": sha.upper()})
        add("sha-substring", {**value, "image_sha256": "0" + sha})
        add("sha-null", {**value, "image_sha256": None}, False)
    if "image_base64" in value:
        add("image-base64-number", {**value, "image_base64": 5})
        add("image-media-type-absent",
            {k: v for k, v in value.items() if k != "image_media_type"},
            False)
    return out


# ------------------------------------------------------------------ 两侧判定


def python_accepts(value: Any) -> bool:
    try:
        ImageWireEnvelope.model_validate(value)
    except ValidationError:
        return False
    return True


def js_accepts(cases: list[tuple[str, Any, bool]]) -> dict[str, bool]:
    with tempfile.TemporaryDirectory() as tmp:
        cases_path = Path(tmp) / "cases.json"
        cases_path.write_text(json.dumps(
            {"cases": [{"name": name, "value": value} for name, value, _ in cases]},
            ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            ["node", PARITY_TOOL, "--cases", str(cases_path)],
            cwd=str(ROOT), capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"JS 侧失败（rc={completed.returncode}）："
                               f"{completed.stderr.strip()[-400:]}")
        document = json.loads(completed.stdout)
    return {item["name"]: bool(item["ok"]) for item in document["results"]}


def check_artifacts_current() -> None:
    """生成物必须可由当前模型逐字节重建，并且是自包含 ESM 具名导出。"""

    schema_file = ROOT / GENERATED / SCHEMA_NAME
    validator_file = ROOT / GENERATED / VALIDATOR_NAME
    missing = [path.name for path in (schema_file, validator_file) if not path.is_file()]
    check("ENVELOPE-ARTIFACTS-PRESENT", not missing,
          {"missing": missing, "hint": "先跑 npm run build:envelope"})
    if missing:
        return
    with tempfile.TemporaryDirectory() as tmp:
        schema_out = Path(tmp) / SCHEMA_NAME
        validator_out = Path(tmp) / VALIDATOR_NAME
        exported = subprocess.run(
            [sys.executable, EXPORT_SCHEMA_TOOL, "--out", str(schema_out)],
            cwd=str(ROOT), capture_output=True, text=True, check=False)
        generated = subprocess.run(
            ["node", GENERATE_VALIDATOR_TOOL, "--schema", str(schema_out),
             "--out", str(validator_out)],
            cwd=str(ROOT), capture_output=True, text=True, check=False)
        check("ENVELOPE-CODEGEN-REPRODUCIBLE",
              exported.returncode == 0 and generated.returncode == 0
              and schema_out.read_bytes() == schema_file.read_bytes()
              and validator_out.read_bytes() == validator_file.read_bytes(),
              {"export_rc": exported.returncode, "generate_rc": generated.returncode,
               "export_stderr": exported.stderr.strip()[-200:],
               "generate_stderr": generated.stderr.strip()[-200:],
               "hint": "改了 v2_image.py 的 ImageWire* 模型后必须重跑 npm run build:envelope"})

    source = validator_file.read_text(encoding="utf-8")
    check("ENVELOPE-VALIDATOR-STANDALONE",
          f"export const {EXPORT_NAME}" in source and "require(" not in source
          and "import(" not in source,
          {"export_present": f"export const {EXPORT_NAME}" in source,
           "require_present": "require(" in source, "bytes": len(source)})


def main() -> int:
    check_artifacts_current()
    if not (ROOT / GENERATED / VALIDATOR_NAME).is_file():
        for name, ok, detail in checks:
            print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
        print("[FAIL] ENVELOPE-PARITY 生成物缺失，无法建立等价矩阵（先跑 npm run build:envelope）")
        return 1

    real = real_responses()
    cases: list[tuple[str, Any, bool]] = [(name, value, False) for name, value in real]
    for name, value in real:
        cases.extend(mutations(name, value))

    js = js_accepts(cases)
    diverged: list[dict[str, Any]] = []
    leaked: list[str] = []
    for name, value, must_reject in cases:
        python_ok = python_accepts(value)
        js_ok = js.get(name)
        if python_ok != js_ok:
            diverged.append({"case": name, "python": python_ok, "js": js_ok})
        elif must_reject and python_ok:
            leaked.append(name)

    accepted_real = [name for name, value, _ in cases
                     if name.startswith("real-") and "::" not in name and python_accepts(value)]
    check("ENVELOPE-REAL-RESPONSES-ACCEPTED", len(accepted_real) == len(real),
          {"real": [name for name, _ in real], "accepted": accepted_real})
    check("ENVELOPE-CROSS-LANGUAGE-EQUIVALENCE", not diverged,
          {"cases": len(cases), "diverged": diverged[:8], "diverged_count": len(diverged)})
    check("ENVELOPE-MALFORMED-REJECTED", not leaked,
          {"must_reject": sum(1 for _, _, flag in cases if flag), "leaked": leaked[:8]})

    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {json.dumps(detail, ensure_ascii=False)}")
    print(f"[{'PASS' if not problems else 'FAIL'}] ENVELOPE-PARITY {len(cases)} 案例 "
          f"（真实响应 {len(real)}，变异 {len(cases) - len(real)}）"
          f"；Python↔JS 判定不同 {len(diverged)}，本该被拒却放行 {len(leaked)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
