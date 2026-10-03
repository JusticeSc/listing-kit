# V2.R4.4 · 冻结执行身份与项目包合同（r44-identity）

> NOT-AUTHORITY: point-in-time verification evidence only.
> 观察时点：2026-10-03T07:28-07:34（本地）。环境：Windows 桌面 Chrome 无头（Playwright），fake 图像/语义 provider + 本机 HTTP 服务；真实模型调用 0 次、外部网络 0 次。
> 本轮任务：V2.R4.4（前置 V2.R4.3 已 done）。state.md `next_action_task: V2.R4.4`。

## 结论

R4.4 四个验收面全部拿到新鲜证据：

1. **冻结执行身份（浏览器 + HTTP）**：`tools/verify_v2_4_2_generation_attempt.py --label r44-identity` 全过（25 checks，status passed）。
2. **网关侧身份核对（服务端）**：`tools/verify_v2_4_1_image_gateway.py --label r44-identity` 全过（退出码 0）。
3. **项目包合同（Attempt 往返 + 旧格式原子拒绝）**：`tools/verify_v2_1_3_project_package.py --label r44-identity` 全过；Z10（attempt 含冻结身份导出→导入逐字一致）、Z11（schema 1 无身份 attempt 整包拒绝、不部分写入）通过。
4. **正式入口不回归**：`app/server.py --check` 38/38 通过（v2.4.2-16 同一轮证据）。
5. **Node 契约**：`node --test attempt-contract.test.mjs config-export.test.mjs` 21 pass / 0 fail。

## 证据文件

- `evals/product-v2/v2.4.2-generation-attempt-20261003-072854-r44-identity.json/.txt/.png`
- `evals/product-v2/v2.4.1-image-gateway-20261003-072955-r44-identity.txt`
- `evals/product-v2/v2.1.3-project-package-20261003-073227-r44-identity.txt`
- `evals/product-v2/node/attempt-contract.test.mjs`、`evals/product-v2/node/config-export.test.mjs`

## 覆盖的验收条目（plan §V2.R4.4）

| 验收原文 | 证据 |
| --- | --- |
| 换设置后已提交 task 不走新目标 | V2.4.2-19/19b：身份漂移 → 核对请求不发、记录零改写、给出原身份与恢复条件；恢复原身份后同 task 核对成功 |
| 同 task 不同 target 不串 | V2.4.2-20：直发网关 mismatch target → 400 EXECUTION_IDENTITY_MISMATCH；target 一致放行 200 |
| 同版本包对象/hash/候选保持 | V2.1.3-03/04/05 + Z10；候选 sha256/字节往返一致 |
| 缺原 key 明确可恢复 | V2.4.2-19（blocked_environment 恢复条件文案）+ V2.4.1-31/32（默认档关闭不阻断 BYOK） |
| 密钥轮换不使无关 Prompt 过期 | V2.4.2-14：Prompt 陈旧度只看 Prompt 版本，凭据变更零改写 |
| 配置导出区分可分享/需重新提供凭据 | V2.4.2-22 + config-export 契约（白名单字段、secret 混入被拒） |
| 旧格式按 §2.3 明确拒绝 | Z11（无身份 attempt 整包拒绝）+ config-export 旧格式拒绝 |
| 不猜身份 | attempt.js 单一词表 `byok/default/none/test_double/env`；读不到有效身份 → environment_unknown，不冒充 |

## 本轮代码修改

- `app/product_v2/workspace.js`：`attemptProviderIdentity()` 入参修正为 images 块（此前误传 provider 块，导致恒 null → 提交静默跳过）。
- `app/product_v2/domain/attempt.js`：凭据来源词表补 `env`（直构探针口径）；harness/node 两份镜像断言同步。
- `src/providers/v2_fake_{image,semantic,review,suite_review}.py`：实例属性补 `credential_source = "test_double"`，与 `capabilities()` 声明同源（能力块读实例属性）。
- `app/product_v2_server.py`：submit/status/result 的 `_image_provider()` 与 `_verify_execution_target()` 收进 ImageFailure 分类捕获（此前构造失败/身份不匹配会击穿 handler 线程 → 连接被关）；`_verify_execution_target` 补 ImageFailure 局部导入（NameError → 500 的直接原因）。
- `tools/verify_v2_4_2_generation_attempt.py`：漂移断言改到生成阶段就近错误元素 `#generate-error`（`#attempt-error` 位于复核阶段面板）。

## 边界（未证明）

- 真实付费模型、真实素材、部署、Git 提交/推送未执行（各自单独授权）。
- 双浏览器独立/双标签冲突、长历史压力属于 R5.1/R6.x 范围。
