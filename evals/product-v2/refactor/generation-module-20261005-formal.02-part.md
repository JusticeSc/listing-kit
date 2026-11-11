<!-- 拆分件 02/03 · 父文档 evals/product-v2/refactor/generation-module-20261005-formal.md -->
# 集成续接：编译、可选同步标志与真实缩放
[返回 generation-module-20261005-formal.md](generation-module-20261005-formal.md)

## 集成续接：编译、可选同步标志与真实缩放

- `build:frontend` 与 `check:generated` 已实际生成/核对六个 TS Module（attempt、config-export、semantic-analysis、session、model-settings、generation）；调用方 app/workspace 的严格检查仍在集成，不宣称 R7.5 完成。
- `v2.5.1-deterministic-review-20261005-212409-r75-c09.json` 保留 B04/B05/B09 失败。根因不是夹具：TS 迁移新守卫要求冻结身份必须写 `sync`，而原实现和合法已存记录允许缺省，缺省即异步；新守卫误判为无身份，已有 task 进不了核对队列。
- 修复 `AttemptExecutionIdentity.sync` 为可选，运行时守卫接受未声明/布尔值；不补造旧身份，也不修改上述失败夹具。编译后同浏览器入口 `v2.5.1-deterministic-review-20261005-212647-r75-optional-sync-fix.json` 全过，包含原失败批次用例、实际候选保存及报告刷新恢复。
- 原先受旧设计约束的 UI2 检查按冻结 UI 合同重基线，`v2.ui.2-interaction-visual-20261005-211310r75prebuild-green.txt/json` 22/22。阶段入口可达不授权业务动作，异步完成后由用户导航；既有键盘/视觉/IDB/错误检查保留，不靠恢复阶段锁或自动导航迎合旧验证器。
- Chrome 默认缩放通过独立临时配置的 `partition.default_zoom_level` 设置，启动参数明确 `--headless=new` 与实际窗口尺寸；125%/1440×900 实测 outer 1440×900、inner 1133×641、DPR 1.25；200%/1366×900 实测 outer 1366×900、inner 671×400、DPR 2。两者 `visualScale=1`、CSS zoom=1、transform=none，不以 CSS 或缩窗口冒充浏览器缩放。
- 在上述两种真实浏览器缩放中，页面导入现有同版本项目、列表打开、native 下载两类 ZIP 均成功，无横向溢出或 page error；200% 下另由 Enter 导航至交付。编译生成 Module 后再次在 200% 页面完成导入、打开和 native 下载，仍为交付 31,117 bytes/5 members、项目 2,369,839 bytes/50 members。截图与下载在 `_stage-amz-control/formal-development-20261005/zoom125-1440-*` 和 `zoom200-1366-*`；证明交互/字节，不证明 fake 候选质量或真人验收。
- 暂存准备中一次浏览器工具调用未明确 headless，进程参数显示缺 `--headless`，发现后关闭并确认进程已退出；该次不计入验收，后续明确验证 `--headless=new`。首次 Playwright 缩放 smoke 采用默认 1280×720 窗口导致尺寸断言失败，改为 `no_viewport=True` 后再验实际 outer/inner；保留失败，不把启动方式或工具窗口默认值当产品缩放缺陷。
- 实现说明的事前原字节快照为 `_stage-amz-control/r75-integration-docs-20261005/`。事前 SHA256：AGENTS `5491c20f592d9c470c154e4d6a8b5152d895de9d64620b1f3223b788d1869eb7`；README `c695de6fb2370ec13a9e85867b19297c8ca1e67053224665baadefe490c7c651`；context `b69f38a1b52b1132aafffb76bc9d4df512512f2e5133ca20a13290dcb744d12e`；state `813cd9a4292070145eb36e359c797e9b93c0b471ba0e929a668693563a453e0b`。本次更新只同步已有产品/编译行为和限制，不改 Goal、预算、真人门或发布准出规则。

## 集成续接：真实看图、载荷边界与拦截异常

- 实际页面第一次看图请求在网关出网前被拒：原理解路由仍按文字请求的 256KiB 限制读取正文，合法的 2,239,735 bytes JPEG 经 base64 后超限。`vision-ui-gateway-body-rejected-no-send.json` 保留失败；该拒绝发生在构造/调用模型之前，不以后来发现有缺口的 SDK 计数器证明零外呼。
- `app/product_v2_server.py` 的理解路由现按现有三张×4MiB 图片的 base64 上界加原文字元数据余量读取；没有改变单图/合计/张数/哈希合同。正式入口原自检新增消费者边界：合法大图成功、身份哈希不符和单图超限均在模型调用前拒绝；原输运超限检查改为真实新边界及响应 details。`uv run --locked python app/server.py --check` 实跑 45/45，输出 `artifact://1210`。
- 首次“离线”SDK 回放存在验证脚本错误：只拦截 `httpx.Client.send`，实际默认客户端由 `httpx2` 派发；虚拟 key 请求返回供应商 401/`PROVIDER_AUTH_FAILED`。原脚本 `model_calls=0` 不可信，该轮不是离线通过。失败完整保留在 `vision-ui-offline-isolation-failed-401.json`；账本保守计一次 SDK 调用并保留 0.23 元未结算预留，不宣称未计费或借重新跑绿抹去异常。
- 修正临时 smoke 的实际 `httpx2` 派发拦截，并在调用前检查 SDK 客户端确实受同一单次守卫控制。同一完整图片通过无联网 SDK 回放：`vision-ui-offline.json` 为 `offline_body_limit_ui_smoke`、真实模型调用 0；这里只证明传输/解析/保存，不证明图片理解质量。
- 随后由真实页面选择 `qwen-vl-max`、提供当前标签页 BYOK、上传登记许可素材，明确发出一次看图理解。实际 SDK 请求携带原上传 JPEG 的 2,239,735 bytes 和完整 SHA256 `c024b7cf2b04d39601a5146664879a5aff8d3fe4cb98b4990bda4c3ae6594461`；供应商/网关均 200、单次调用、无 page error。`vision-ui-live.json/png` 记录真实页面及请求。12 个模型槽位均为 proposed/model_inference，没有自动确认；截图显示模型提案、逐槽位确认和仍缺的结构化尺寸。
- 真实理解项目 ID 为 `e80ddebc-0b34-4079-a34b-6758ac891e55`。最后一版 semantic_analysis 为 version=3、succeeded/applied；原资料 version=2 的完整 payload/fingerprint 包含上述完整资产 hash。模型 evidence 展示使用哈希短标签，原资料快照保留完整身份，不把短标签当完整 hash。该脚本关闭临时 profile 前只保存理解阶段 JSON 投影和截图，没有 native 导出此项目；因此不能把这一成功宣称为 §14.9 完整图文辅助任务或其 ZIP 往返通过。
- 供应商返回 prompt_tokens=2549、completion_tokens=1479；按本轮已核官方价格估算 0.0099944 元，不是账单确认。成功调用的 0.23 元预留和 401 异常的 0.23 元预留均未释放。账本现保守计生图 8、语义/VLM 5、合计 13；本轮补充调用 2/3，增量预留 0.46/1 元，累计预算占用 1.61/5 元，既往 spent_cny=1.15 不清零。
- 另一次调用前页面 create-project 持续 disabled、没有模型请求；`vision-ui-transient-startup-disabled.json` 仅保留断言位置与当时零请求，未取得该失败的 UI 阶段轨迹。后来可用样本不解释这次失败，也不关闭历史 RC19；仍按 §7.6查证现象—机制。
- App 严格调用方检查已由该切片交付零本文件诊断。实际页面复现活动项目改名错误 `workspace is not defined`：名称已落库但页面报错；源码改由 Session 更新当前项目元数据，保留项目/generation，不重开工作区。Session 新方法尚待统一编译后同页面重验；workspace 严格调用方切片与发布事务切片仍未集成，完整 Goal/最终两轮回归/发布均未完成。

本节 `vision-ui-*` 相对路径均位于 `_stage-amz-control/formal-development-20261005/`；预算唯一在 `_working/amz-listing-kit-product-v2/budget-ledger.json`，不据本报告再次发起付费调用。

