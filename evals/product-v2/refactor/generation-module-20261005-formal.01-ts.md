<!-- 拆分件 01/03 · 父文档 evals/product-v2/refactor/generation-module-20261005-formal.md -->
# 正式开发：人工纵向主链与首批 TS 产物
[返回 generation-module-20261005-formal.md](generation-module-20261005-formal.md)

# 正式开发：人工纵向主链与首批 TS 产物

> NOT-AUTHORITY: point-in-time evidence。目标/任务仍看产品计划，当前恢复点只看 state；本文不宣布完整 Goal、R7.5、图文能力或发布完成。

## 实际交付

- `app/product_v2/generation.js` 的 `confirmAndRun` 统一保存生成授权并执行批次；`workspace.js` 的首次生成和返工都切换至该入口，UI 不再另走保存授权/开始批次的旧路径。
- 修复受控 A→B 项目切换下的旧回调串扰：候选按原 Attempt/项目落库，原执行链和 flight 集合由回调持有，不清除 B 的进行中动作。`generation-isolation.test.mjs` 先失败、修复后通过；核对原项目候选动作/hash与新项目未被写入，而不是仅断言不抛异常。
- `domain/suite-review.js` 的依赖硬门只覆盖必需或已采用用途；未采用的可选尺寸草案不阻止主图交付，必需/已采用尺寸图仍被缺尺寸阻断。报告输入指纹包含 `dependency_scope=required_or_selected`，旧报告不能沿用新语义。`suite-dependency-scope.test.mjs` 覆盖正反边界。
- 交付 `manifest.json` 及 `checks.json` 的整套/每图增加真实 `ai_review` 投影；无 AI 调用为 `status=not_reviewed, reason=not_run, checked_at=null`，不伪装成 PASS/模型 Unknown。复用现有 `suiteReviewStatusOf`，没有放松确定性报告、采用与完整性门。
- `domain/attempt.ts` / `domain/config-export.ts` 是首批唯一手写源码，同名 JS 由现有锁定 TypeScript 编译。新增 `build:frontend` / `check:generated`；服务只提供生成 JS，TS/d.ts 返回 404，Docker 构建上下文排除 TS。编译器不进入生产运行时。README/context 已同步；session/model-settings/generation 的 TS 迁移仍在进行，不能把首批成功称为 R7.5 完成。
- 人工事实、结构化尺寸、按用途绑定与精确 Prompt 失效已有产品实现，未重复建设。四份过期 Node 孪生同步至当前浏览器行为合同；只改断言体的消费者行为，不重钉文案/实现名。

## 实际页面与字节证据

独立临时配置的 Chrome 无头，仅本地 fake provider，无付费、无系统键鼠。

1. 页面新建商品任务，上传已登记公开许可蜂蜜罐原图，人工确认核心事实，不发商品分析。
2. 选择主图/场景图及缺尺寸的可选尺寸草案；主图/场景图自动本地准备，同一发送摘要一次确认生成两个候选。
3. 页面打开比较、人工采用；主图就地返工，原主图采用和无关场景图采用未改变；网络未出现自动商品分析/AI 复核。
4. 未采用尺寸草案最初错误阻断整套交付；上述依赖范围修复后，运行真实本地确定性报告，无 AI 复核生成交付与完整项目包。
5. 管理浏览器的下载等待没有证明 native 下载成功，未把 blob 捕获当 native 下载。随后全新临时 Chrome 配置导入实际项目包，点击列表打开项目，在正式页面实际完成两类 native 下载。
6. 交付 ZIP：31,117 bytes，5 members；项目 ZIP：2,369,839 bytes，50 members。无 page errors。截图、原包、下载及 JSON 在 `_stage-amz-control/formal-development-20261005/`。
7. 对下载包逐项核对：主图原采用候选 `act-144e4fba7b214ffdadecf9453e7b02ad` 的 SHA256 为 `9d34b3e53e06250b60c06248c7848383e5771867b8c8f3954156679d9e8e4cd5`；场景候选 `act-73499842a25441c6be9a3f48d9205923` 为 `63aac5275511fba00cb93ebe33369fe462256f3a175d7f5fda31d389f3fd0467`。二者字节长度/hash 与清单一致。
8. 项目包导入后再导出：源包 44 份文档按 kind/id/version 逐份 JSON 相等，全部 4 个资产逐字节相等且 SHA256 正确，仅多 1 份本次交付 export_record。manifest/checks 整套及每图均如实 not_run。原始核对结果：`_stage-amz-control/formal-development-20261005/zip-integrity.json`。

## 本批实跑与失败记录

- `npm run build:frontend`：实际生成两个 TS 对应 JS。
- `npm run check:types` / `check:generated` / `check:versions`：通过。覆盖仅 jsconfig 明确登记 TS 和已 opt-in 的 JS；未检查的依赖 JS 不宣称有类型保障，已迁 Interface 的调用方检查尚须后续完成。
- 仅运行直接受影响 Node 文件：attempt、config-export、suite-plan、suite-editor、prompt、prompt-edit、generation-isolation、suite-dependency-scope。71 条通过；未运行本轮最终两轮完整回归。
- `uv run --locked python app/server.py --check`：42/42，通过；实际 TS/d.ts 404、生成 JS 200。
- `package-smoke.py` 最初把导入误当自动打开而超时；按真实列表“打开”交互修正后通过。
- 新增 manifest 投影后的第一次下载超时；发现缺少 `suiteReviewStatusOf` 导入并补齐，之后同一路径 native 下载通过。失败原输出保留于会话工具产物 `artifact://926`，不把后来绿样本抹成无失败。
- Python Eval 后端不可用；字节核对改用已锁定 uv 的原生 Python 子进程，实际 exit=0。不是产品故障。

## 范围与准确下一步

上述 fake 候选只证明离线流程/保存/hash/交付，不证明真实图像质量、两供应商本轮补证、真人走查或线上发布。R6.1 人工部分可用；图文实际能力、原资料快照/迟到结果隔离仍需闭合，整项不能 done。R6.2/R6.3 的人工交付路径成立，完整设置/恢复/视口/键盘验收仍未全部成立。R7.5 后续 session/model-settings/generation 正在迁移且尚未集成检查；R7.1 最终回归与 R7.4 发布保持未完成。

继续：完成正在迁移的 Module 及实际消费者检查；复用现有人工项目闭合图文辅助的原快照/迟到回调，再按计划最终集成。保持原预算账本，未执行新增付费、Git 提交/推送/PR 或发布。

## 集成续接：失败保留与当前证明边界

- 串行集成检查保留两个失败：V2.2.3 分析后点击隐藏的理解区控件超时；UI3-16 的真实错误摘要缺少重试策略。当前 UI 合同 §2.6/§3 明确异步结果不自动导航，因此没有用自动切阶段迎合旧验证器。
- V2.2.3 改为用户显式导航至理解区；`v2.2.3-intake-understanding-20261005-205150-r75fix2.txt` 实跑全过。分析失败摘要补齐策略、Unknown 保留不自动重试；此前失败证据与后续结果分别保留，不把旧失败擦成绿色。
- Node 域孪生本轮先出现 219/226、7 条失败；已按当前消费者合同处理候选批次夹具、合法旧采用和复核超限，不改变产品来迎合旧断言。后续 226/226 是领域行为范围，不证明页面、真实模型或最终两轮回归。
- `generation.ts` 首次纳入检查时出现 4 个类型诊断：复核条目的 null/undefined 边界及未迁确认函数的 JS 推断签名。对应修正后一次 `npm run check:types` 零诊断；生成 JS 尚待统一编译及实际页面验证。
- 对实际调用方单独开启严格检查的测量发现 `app.js` 140 个、`workspace.js` 1121 个诊断；原绿色类型检查未覆盖这两个调用方。正按既有 JS 添加严格检查与具体类型，不机械改名或宣称全仓 TS；R7.5 仍未完成。
- 本机 `docker version` 有 CLI、无可连接的 Linux daemon；`tools/release_transaction_probe.py --selftest` 实际返回 exit 2，ST-01 `missing_prereq: docker info failed`。这不是回退已通过；未启动可见 Docker Desktop，后续须在已批准的具备 Docker 的运行通道证明事务。
- 真实图文调用前只核对公开准入：阿里云 [qwen-vl-max 官方模型页](https://help.aliyun.com/en/model-studio/qwen-vl-max) 给出北京输入 1.6 元/百万 token、输出 4 元/百万 token，最大输入 129024、最大输出 8192；当前 Adapter `max_tokens=5000`。按全输入上界及当前输出上界计算为 0.2264384 元，后续可用 0.23 元保守预留；本次尚未预留或发起付费调用。
- [蜂蜜罐来源页](https://commons.wikimedia.org/wiki/File:Antique_Glass_Honey_Jar_With_Rusted_Metal_Cap_(31009798197).jpg) 本轮重新核对为 Cindy Shebley / CC BY 2.0。实际发送候选素材是已保存 3840×2560 缩略图，SHA256 `c024b7cf2b04d39601a5146664879a5aff8d3fe4cb98b4990bda4c3ae6594461`；不是 5575×3717 的原站文件，记录来源和缩略版本，不冒称原站原始字节。Adapter 必须发送这份用户上传素材的真实字节，不以元数据代替看图。
- 历史启动/重开失败仍缺现象—机制归因，原日志只证明重开列表行数为 0；已知 readiness/读取恢复修复与后续绿色不自动关闭 RC19。保持发布门，不自行接受风险。

