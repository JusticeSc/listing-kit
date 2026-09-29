# 欠费错误的可执行提示（Provider 错误面）

> EVIDENCE-SNAPSHOT: current · NOT-AUTHORITY
> 归属：D1.1（语义 provider）/ D2.1（图片 provider）/ D4.1（清晰错误）。任务定义只在 `docs/product-demo-goal-and-implementation-plan.md`。

## 问题（修复前）

百炼账户欠费时上游返回 HTTP 400 + `code=Arrearage`，产品把它当成普通上游拒绝：

- 语义：`UPSTREAM_REJECTED`，「百炼拒绝本次请求（HTTP 400）；详情摘要已脱敏保存。」
- 图像：`UPSTREAM_REJECTED`，「百炼拒绝了图像提交请求（HTTP 400）（服务码 Arrearage）。」

用户看不到“要充值才能继续”，也没有可执行修复动作。

## 修复（本轮改动）

- `src/providers/__init__.py`：新增 `is_arrears_provider_code()`（`arrearage` / `arrears` / `overdue`，大小写不敏感），作为两个适配器共用的判据。
- `src/providers/dashscope_semantic.py`：非 2xx 且服务码命中欠费 → `UPSTREAM_ACCOUNT_ARREARS`，文案说明“本次请求未被受理、工作空间未改变、充值后重试即可”，`recoverable=True`；诊断摘要仍只保留脱敏字段（HTTP 状态、字节数、sha256、provider_code）。
- `src/providers/dashscope_image.py::_upstream_error`：同样分类；提交类操作 `status=FAILED`（未被受理，充值后可安全重试同一张），查询/下载类保持 `REJECTED` 语义不变。
- `src/application_service.py`：三个语义 catch 点把 `UPSTREAM_ACCOUNT_ARREARS` 映射为 HTTP 503 + `next_action=recharge_dashscope_account_then_retry`。

## 验证（新鲜证据）

1. 离线单测（无网络）：
   - `tools/verify_semantic_provider.py`：11 tests OK，含新增 `test_account_arrears_is_reported_with_an_actionable_message`；
   - `tools/verify_dashscope_image_provider.py`：10 tests OK，含新增 `test_account_arrears_maps_to_actionable_failed_submit`；
   - 两个新用例均断言不泄漏 `PRIVATE_PROMPT_SENTINEL` / `SECRET_API_KEY`，并保留 `request_id`。
2. 真实链路（8789 端口，加载最新代码；上游账号仍处于欠费状态）：
   - `POST /api/product-brief/draft` → **HTTP 503**；
   - `code=UPSTREAM_ACCOUNT_ARREARS`；
   - `message=阿里云百炼账户欠费（服务码 Arrearage），本次请求未被受理，工作空间未改变；充值后重试即可。`；
   - `next_action=recharge_dashscope_account_then_retry`；
   - `request_id=e86c9e2c-fb8a-95a4-ac7b-5004665ca745`；
   - 上游直接拒绝、无任务号返回；工作空间 revision 保持 `3680e34dba1225aa16b2aa2e0df01c82353cc3692141dfe88cc0547d0be77219` 未变。

## 局限

- 只识别 DashScope 的欠费类服务码；其他计费类错误变体（未观测到）仍走通用拒绝文案。
- 前端未对 `next_action` 做专门分支，只呈现 `message`（该文案已包含可执行动作）。
- 图像端口的真实欠费响应尚未观测到（见下节实测），图片路径的欠费分类目前只有离线单测覆盖。

## 2026-09-29 00:08 补充实测：欠费只拦住语义模型，图像模型仍能出图

为分辨“欠费到底拦住了什么”，把 run-05 工作空间复制到临时目录（`C:\Users\31368\AppData\Local\Temp\amz-arrears-image-check-000816\workspace`，原工作空间未改动），通过 8789 端口真实调用：

- `POST /api/generation/start`：4 张图中 **2 张被上游受理**（拿到真实任务号 `686a0be6-6119-4ca1-b8cd-1f4f1bfe46e6`、`4168dc19-af19-482f-9e33-67a5e5d4b3e8`），另 2 张返回 HTTP 429 `Throttling.RateQuota`（限流，明示“这次提交没有被受理”）。
- `POST /api/generation/reconcile`（带两个 action_id）：两个任务都 **SUCCEEDED**，候选图已真实下载入库（1.7 MB / 2.7 MB PNG）。
- reconcile 后各图候选数：主图 2、纹理特写 2、垂感展示 1、场景图 2；其中 4 个候选是本次新建的。

结论（证据支持）：

- **语义模型（qwen3.7-plus）被欠费阻断**：`UPSTREAM_ACCOUNT_ARREARS`（见上节，request_id `e86c9e2c-…`）。
- **图像模型（qwen-image-3.0）当前仍可提交并真实出图**，至少在本观测窗口内；因此已有方案+提示词的工作空间仍能走“一键生成 / 单张返工 / 选择 / 导出”。
- 从空白新建商品（商品理解 → 方案 → 提示词）需要语义模型，**在充值前走不通**。
- 图像端口的 429 是限流而非欠费，产品按“未被受理、稍后重试这张”呈现（与既有设计一致）。
