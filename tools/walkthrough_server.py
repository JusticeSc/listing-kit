#!/usr/bin/env python
"""产品发起人走查服务器：正式入口 + 确定性 fake provider，按提交顺序注入「部分失败 + Unknown」。

用途：让走查者不接模型、不产生费用，也能在真实界面上看到并处理：
  - 正常成功；
  - 单张明确失败（FAKE_CONTENT_REJECTED，可用界面里的「重试」恢复）；
  - 单张没有任务编号的 Unknown（系统不自动重提，只能用界面里的显式新建 action 恢复）。

它复用 `app/product_v2_server.py` 的正式处理器与 `app/product_v2/` 静态资源，不修改产品代码；
产品服务端仍然无状态，进程内保存的只是「第几次提交 → 哪个场景」的走查剧本。本工具只服务走查，
不挂 /harness/，不进 CI，也不属于产品入口。

剧本（按新 action_id 的提交顺序；重复提交同一 action_id 复用同一场景）：
  第 1 次 → 成功
  第 2 次 → 明确失败
  第 3 次 → 提交结果未知（provider_unknown，无任务编号）
  第 4 次及以后 → 成功（重试与「新建 action」都因此可恢复）

运行：
  uv run --locked python tools/walkthrough_server.py --port 8778
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.product_v2_server import create_product_v2_server  # noqa: E402
from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_fake_review import FakeReviewProvider  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402

SCRIPT = ("ok", "failed", "submit_unknown")


class WalkthroughImageProvider(FakeImageProvider):
    """按提交顺序执行走查剧本；同一 action_id 幂等（同 action 同结论）。"""

    def __init__(self) -> None:
        super().__init__("ok")
        self._lock = threading.Lock()
        self._scenario_by_action: dict[str, str] = {}
        self._scenario_by_task: dict[str, str] = {}

    def _scenario_for(self, action_id: str) -> str:
        with self._lock:
            known = self._scenario_by_action.get(action_id)
            if known is not None:
                return known
            index = len(self._scenario_by_action)
            scenario = SCRIPT[index] if index < len(SCRIPT) else "ok"
            self._scenario_by_action[action_id] = scenario
            self._scenario_by_task[self.task_id_for(action_id)] = scenario
            return scenario

    def submit(self, request):  # noqa: ANN001 - 与 FakeImageProvider 同形
        self.calls["submit"] += 1
        self.scenario = self._scenario_for(request.action_id)
        return super().submit(request)

    def status(self, request):  # noqa: ANN001
        self.calls["status"] += 1
        scenario = self._scenario_by_task.get(request.task_id, "ok")
        self.scenario = scenario
        return super().status(request)


def main() -> int:
    parser = argparse.ArgumentParser(description="V2 走查服务器（fake provider；注入部分失败与 Unknown）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8778)
    args = parser.parse_args()

    image = WalkthroughImageProvider()
    server = create_product_v2_server(
        args.host, args.port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: image,
        review_provider_factory=lambda: FakeReviewProvider(scenario="ok"))
    print(f"走查入口：http://{args.host}:{args.port}/"
          "（第 1 张成功 / 第 2 张明确失败 / 第 3 张 Unknown，重试与新建 action 均可恢复）",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
