NOT-AUTHORITY: point-in-time evidence; not a plan, current state, or product completion

# V2.R1.2/R1.3 可达材料 · 20261001-211200Z

## 本轮真实运行（全部离线、无密钥、无网络模型）

- `evals/product-v2/v2.1.2-project-home-20261001-210254-offline-ui1.{txt,json}`：11/11 通过。空白启动、项目 CRUD、重命名/复制/删除、刷新恢复、双 profile 隔离、390px 无横向溢出、全程无 console/page error、V1 路由未破坏。
- `evals/product-v2/v2.1.3-project-package-20261001-210313-offline-ui1.{txt,json}`：8/8 通过。项目 ZIP 的标准 ZIP/CRC、manifest 与资产哈希、清空后逐项一致、重复导入新 ID、损坏包拒绝且不污染。
- `evals/product-v2/v2.2.3-intake-understanding-20261001-210323.{txt,json}`：22/22 通过。正式入口 + fake-semantic 下空白到资料确认、一次 POST、无隐藏重提、冲突保留旧值、PLAN_REVIEW 推进、键盘与窄屏、会话前后磁盘零差异。
- `evals/product-v2/v2.6.3-transfer-20261001-210935.{txt,json}`：13/13 通过。格式 2 导出、跨 profile 逐文档/资产哈希一致、迁移后可返工/交付、格式 1 旧包升级提示。
- `evals/product-v2/v2.4.1-image-gateway-20261001-211006.{txt,json}`：全部通过。四类离线链中语义/提交/查询/取回与输入拒绝、Unknown、未配置、磁盘零差异；注册表可在默认与 fake-image 之间选择。
- 直接网关 smoke（未落盘、仅本次输出）：`/api/v2/capabilities` 四个 provider 身份为 `fake-semantic`、`fake-qwen-image`、`fake-review`、`fake-suite-review`；语义返回 2 个槽位；同一 fake 任务提交/查询/取回/单图复核/整套复核全部 `ok`，`FakeImageProvider.calls` 为 `{"submit": 1, "status": 1, "result": 1}`。

## 与旧阻塞的对应关系

- `R1_3_offline_audit_four_provider_isolation_not_verified`：本轮已用真实入口证明四 fake 可走同一产品路径；但 `tools/v2_test_server.py` 默认只注入语义 fake，仍不是四类默认隔离。后续离线审计必须显式注入四 fake 或使用上述已验证的显式构造，不依赖默认回落。
- `R1_2_recoverable_old_package_and_multi_candidate_project_baseline_missing`：仍未关闭。交付包（`rehearsal-exports/` 17 个、`real-e2e-091400/delivery-091400.zip`）只含交付内容，不能替代完整项目历史包；旧临时完整包已不可达；format-1 旧包只有合成迁移用例，缺真实旧包工件。本轮新增证据仍是本地过程材料，未按 §7.1 精确提升，未提交。
- Boot 间歇失败：本轮三次浏览器套件（V2.1.2/V2.1.3/V2.2.3）与迁移/网关套件全部一次通过，但这是“本次离线绿”，不是对 061430 失败样本的根因闭合。root cause 保持未知，R3.3/G3 门保持。

## 未证明

真实模型、第二模型、BYOK、默认档策略、旧任务历史身份冻结、C17/C15、V1 日落、部署/线上。本轮无付费调用、无私有素材上传、无提交/推送。
