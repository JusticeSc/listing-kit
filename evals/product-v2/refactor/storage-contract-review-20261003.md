NOT-AUTHORITY: point-in-time evidence only, not a plan, current state, or product completion.

# V2.R6.4 存储与合同测量复访（2026-10-03）

输入：repository 全历史读、代表长历史、跨语言词表/schema（计划 §9 V2.R6.4）。
方法：隔离 Chrome 154 headless、本机正式入口 `app/server.py --port 18784`、
产品主世界 CDP `Runtime.evaluate` 的 IDB/Blob 只读观测、`Runtime.getHeapUsage` 采样；
0 次供应商调用、无新依赖。打开/资料保存经真实 UI；导出直调 UI 使用的 `exportProjectPackage`。

以下 §1–§5 保留批准前的测量与结论，不是索引施工后的当前结论。用户随后批准改造；
正式实现、同一压力包复测与新鲜验证见 §6；执行进度仍只以 state 为准。

## 1. 读路径（调用点 → 文件:行 → 触发时机）

- boot：app.js boot() → session.js boot()（openStorage → pointer.get → workspace.open）。
- open：handleOpen（projects.get → pointer.set）→ workspace.open → loadWorkspace（打开唯一全量装载序列）。
- refresh：app.js refresh() = projects.list() 全表 getAll + JS 排序（repository.js:112-119，
  索引 by_updated_at 未被使用）；任何首页显示/项目变更触发。
- save：documents.save（repository.js:244-289）事务内先按 by_project_document getAll
  该文档全链算 currentVersion（:261-263），OCC 期望版本比对（:264-273），再 append（:275-286）。
  读放大 = 该文档链长。任务/槽位/报告等追加写不带 expectedVersion（永不冲突，由领域判新旧）。
- open 主路径 loadWorkspace：14 次 documents 查询，全部落在 by_project_kind /
  by_project_document 索引 getAll，索引键不含 version——每次 listLatest 实际读入该 kind
  全部历史版本再在 JS 里 reduce 出最新版；getLatest/listVersions 读单文档全链。
  参考图每张一次 assets.get（Blob 全量）；ensureReviewReport 可能读 Blob + 写报告；
  deriveAndApplyState 可能写 project.state（revision++）。
- export：transfer.js exportProjectPackage（projects.get → documents.listAll →
  assets.list → 逐资产 blob.arrayBuffer() 全量字节入内存）→ package.js buildProjectPackage；
  manifest.integrity 仅表示包内容字节，不能作为实际内存峰值；内存证据见下面 CDP 采样。
- import：transfer.js importProjectPackage（事务外 parse + 哈希校验 → 单事务
  projects + documents + assets 写入）；失败 abort，无半份项目。

事务语义：projects.revision++（rename/setState）；documents append-only + OCC；
assets 内容寻址去重（同 project_id + sha256 已存在直接返回既有，不重复存）。
指针：localStorage 仅 {project_id, updated_at}（pointer.js，MAX 512B）；损坏即清除返回 null。
单文档上限 MAX_DOCUMENT_BYTES = 1MB（validate.js:9）。

## 2. 正式路径实测与原始证据

原始结果：[storage-measurements-20261003.json](storage-measurements-20261003.json)。
包含逐请求记录/JSON payload 字节/Blob 实读字节、逐时刻堆采样、原始观测与执行源码、
代码及配置 SHA256、种子清单、独立索引 PoC 与往返/OCC/哈希拒绝结果。
原报告缺乏这些原始证据；其结论已被本节取代，原文保存为
`storage-contract-review-20261003-before-path-measurement.txt`，不作通过证据。

种子基线：真实产品历史包导入后 63 文档、JSON payload 106822 B、6 资产。
压力种子：保留真实领域 payload，suite_plan 2000 版、prompt_version 500 版，
共 2560 文档/6913838 B payload；10 资产/14474958 B，其中 4 张为合成压力 PNG。
种子操作超时后先只读核对最终状态，未重放写入。各保存轮次会追加版本，数量随轮次变化。
成功往返的压力副本已保存为 `packages/r64-long-history-pressure-20261003.zip`：
22405248 B、2563 文档、10 资产，SHA256
`86d13d4aabea512af815179164aefbb9218244376f84d1f46f078b7ece978300`。
独立 Python 解包核对全部 CRC/资产 hash 与 suite 的 1–2000 完整数值版本链通过；
保存的是成功导入副本（新项目 ID/导出时刻），不是原先 adb… ZIP 的相同容器字节。

| 正式路径 | 无字节统计的延迟 | trace 读取记录/请求 | trace payload 字节 | memory 轮 CDP 堆采样最大值 |
|---|---:|---:|---:|---:|
| 基线打开 | 70.5 / 70.9 ms | 冷打开 78 / 38 | 105820 B | 4910680 B |
| 基线资料保存 | 28.5 ms | 4 / 2 | 840 B | 3426884 B |
| 基线完整包导出 | 7.1 ms | 70 / 3 | 106801 B | 3814240 B |
| 长历史打开 | 154.1 / 154.2 ms | 2582 / 42 | 6913838 B | 10370348 B |
| 长历史资料保存 | 27.8 ms | 7 / 2 | 1822 B | 3538168 B |
| 长历史完整包导出 | 220.3 ms | 2574 / 3 | 6914822 B | 见隔离导出采样 |

资料保存只追加较短 product_input 历史，不能代表长 suite_plan 链。
单独实测 suite_plan 保存：无统计 59.1 ms（2003→2004）；
trace 86.9 ms、读 2005 条/2815620 B（含项目记录）；
memory 59.7 ms、CDP usedSize 最大 8712052 B（2005→2006）。
压力打开只实读 28004 B 已引用 Blob；未引用压力图片不加载，不能把它称为 14 MB 图片打开压力。
完整导出会实读全部 14474958 B Blob；ZIP 为 22405248 B。

峰值定义：每轮 CDP `usedSize` 与 `backingStorageSize` 的观察最大值，**不是精确峰值/RSS**，
两项不简单相加。采样及包装器有开销；同步 JS 段可能漏采，结果是观察下界。
trace 模式 JSON 序列化用于统计字节，会扰动延迟/内存；memory 模式不做字节统计。
隔离一次导出前删除上一轮保留的 ZIP 并 GC：17 个 CDP 样本，起始堆 3470528 B、
backing 988420 B，最大堆 15312340 B、backing 45603362 B，341.7 ms。
之前连续导出保留的 ZIP 导致较高 backing，原始值保留但不当作单次导出峰值。
早期 isolated-world 观测读数为 0 的轮次已排除；自动化下载被取消，未声称下载落盘通过。

## 3. 判定：最新版索引有收益，批准前不应用

- 同一份 2566 文档、suite_plan 最新版 2003 的隔离原生 IDB PoC：
  现有 getAll 最新查询 53.3–60.1 ms、物化 2003 条；
  数值复合索引反向游标 0.3–1.2 ms、物化 1 条，五次结果全部相等。
- “OCC 必须读取全部历史”不成立；只需在同一读写事务中取得真实最大版本再比较。
  原生索引由 IDB 原子维护，不需要另建 latest 表或双写业务权威。
- PoC 使用临时数据库，已删除；未改生产 schema、repository 查询、包格式或浏览器数据。
  按计划“有收益且批准才改造”保留 R6.4 未完成，下一决策是是否批准索引/schema 改造。
- 建议范围仅为最新版与 OCC 取头查询；listVersions/listAll 和完整包仍保留全部历史，
  不把全历史读换成逐条游标，不虚报正式路径已经变快。普通短历史下收益仍有限。
- projects.list 的项目级排序和跨语言全面 schema 生成不在本次改造范围。

## 4. 跨语言合同/中立表示复访

- 三层合同：浏览器 domain/*.js（业务规则唯一权威）→ storage/*.js（记录/包格式权威）→
  src/providers/v2_*.py（传输与模型 IO 权威）；一致性靠“同常量各写一份 + 验证器正则现场取值比对”
  （V2.2.2-01 / V2.5.2-02 / V2.5.5 / V2.6.3 四组），本轮只读确认，未发现漂移。
- 中立表示已存在：ZIP manifest（format_version=2 自描述记录信封）+
  /api/v2/*/capabilities 的 contract 字段。Pydantic 侧只有运行期 schema 注入
  （json.dumps(Model.model_json_schema()) 进系统提示），无落盘 schema 导出——
  本任务评估的“正在修改的传输合同”即 manifest v2 信封，其已有中立表示可用，无需新增导出。
- 未提交改动方向（harness/* 瘦身 + node/ 分层，R3.2 产物）与本任务无冲突：包往返语义未变，
  V2.1.3 本轮仍全过（见 state phase 3 证据链）。

## 5. 验收对照（V2.R6.4）

- 正式打开/保存/导出已测量，原始读数与源码/hash 可独立复核；导出下载落盘未验证。
- 压力包往返文档及资产全部一致；ZIP SHA256 为
  `adbaba7f24982a870981bcb6915fe146ada19b517b4508d7f4d6703b455f5ed7`。
- 旧版本 OCC 写入返回 REVISION_CONFLICT，版本未变；重复资产保存未增加条目。
- 初始随意翻转 ZIP 字节的包仍被接受，不算损坏拒绝证据；
  重新构造“资产改变而 manifest hash 不变”的包返回 PACKAGE_HASH_MISMATCH，项目数 4→4。
- repository 仍是唯一业务读写入口；零正式 schema/记录格式改造、零兼容层。
- R6.4：测量与原始证据已补齐；索引改造决策/批准及应用后的新鲜回归尚缺，不能标 done。
- 本机合成压力不代表用户满载/配额、真实供应商质量或人工走查。

## 6. 获批原生索引施工与验证

- 授权：`owner-decisions-20261003-index-volcengine.json`；只改最新版/OCC 查询，
  保留完整历史、资产、原子事务与用户数据，不建 latest 双写表、不新增依赖。
- 数据库结构版本 1→2：追加 `by_project_document_version`
  `[project_id, kind, document_id, version]` 数值复合索引；v1 索引集合冻结，
  新索引只在 versionchange 事务的 v2 步骤创建。记录 schema、项目包格式不变。
- `documents.getLatest` 与保存时 OCC 版本头：倒序游标仅取一条；
  `documents.listLatest`：每文档读取一个版本头后跳过该文档历史；
  `listVersions`、`listAll`、导出、复制和删除路径不变。最新版列表保留原 localeCompare 排序。
- 输入仍是已保存的 `packages/r64-long-history-pressure-20261003.zip`，
  SHA256 `86d13d4aabea512af815179164aefbb9218244376f84d1f46f078b7ece978300`，
  原始 2563 文档、10 资产、suite_plan 1–2000 完整历史。

### 6.1 实际运行测量

正式入口 `app/server.py --port 18785`、独立临时 Chrome headless profile。
打开与资料保存实际点击产品控件；导出直调产品 UI 使用的 exporter，未测下载落盘。
游标 success 事件纳入读取计数，源码与全部原始样本见
`native-index-verification-20261003.json`；实际表面见 `native-index-pressure-ui-20261003.png`。

| 场景 | 观察结果 |
|---|---|
| 同一压力库、同一 suite_plan 第 2003 版版本头 | 保留旧全历史算法的 listVersions 读取 2003 条、62.8ms；新 getLatest 读取 1 条、0.7ms；返回版本及载荷相同。两者为 trace 样本，不是整体 UI 速度保证 |
| 实际工作区打开 | 冷启动首次 3151.8ms 保留；暖样本 70.6/101.2ms；trace 样本 70 条、86397B JSON。前一报告跨会话数据不能充当严格配对的打开加速基线 |
| 实际资料保存 | latency 35.8ms；trace 31.3ms、2 条、329B JSON；追加版本可见 |
| 2000 版规划 OCC 保存 | 2000→2001 latency 4.1ms；2001→2002 trace 1.1ms、2 条；2002→2003 memory 1.7ms |
| 完整历史导出 | latency 350.5ms；trace 2577 条、6915806B JSON；memory 样本 JS heap 最大 18774140B。仍导出全历史，不声称优化导出或降低进程峰值 |
| 压力原始数据与往返 | 原 2563 文档逐字段、10 资产逐 SHA256 均不变；合法新增 6 版本后，2569 文档全量导出/导入一致；ZIP SHA256 `3ef4b042cc6464121c0372e3f221db018a781a7d25a527cba95277ae1161e760` |

峰值是 CDP `Runtime.getHeapUsage` 离散采样的下界，不是 renderer/browser RSS 真峰值；
JSON/Blob 字节统计不是内存峰值。错误等待、不可点击节点与误用包字段均为测量脚本错误，
已保留在原始证据的 `harness_errors`，不冒充产品故障或有效测量；未靠重跑删除失败记录。

### 6.2 新鲜验证与恢复边界

| 验证 | 结果 | 证据 |
|---|---|---|
| IndexedDB 契约 | 30/30；含真实 v1→v2 的数值 9/10/100、相邻文档/空查询、历史/资产/元数据保留与并发 OCC | `../v2.1.1-indexeddb-20261003-032509-native-latest-index.json` |
| 项目包与实际 UI 下载/再导入 | 8/8；6 个宿主合同全过 | `../v2.1.3-project-package-20261003-032510-native-latest-index.json` |
| 生命周期 | 15/15 | `../v2.3.3-session-lifecycle-20261003-032515-native-latest-index.json` |
| 正式入口、重开、服务重启、隔离与磁盘 | 13/13 | `../v2.1.4-formal-entry-20261003-032824-native-latest-index.json` |
| 开发类型/领域行为 | 既有 jsconfig 作用域零诊断；223/223，不是全 app strict 审计 | `native-index-frontend-checks-20261003.txt` |

恢复代码保存于 `_stage-amz-control/native-index-20261003-before-reconstructed/`：
修改后反向重建的三个完整文件与先前实测物理 SHA256 一致；明确不是编辑前现场快照。
应配套原压力 ZIP 在独立 profile 恢复，不承诺 v2 原地降级到 v1。
控制面另保存编辑前快照 `_stage-amz-control/native-index-20261003-before/`；
blocked 恢复点必须有同任务 ID 的明确阻塞条目且计划依赖已满足，绝不绕开 PoC 权限。

R6.4 的存储施工、正式路径测量、同版本历史/OCC/资产/包合同与中立合同复访已有匹配证据。
下一门是 R4.2：大陆 Volcengine 仅选定方向，准确模型、数据条款、素材 hash、
本地凭据通道、调用数与总预算仍未获批。整项 Goal、真实模型主链、人审与发布均未完成。

### 6.3 本轮收尾

- 用户要求准备结束工作后，停止扩展施工；本轮隔离 Chrome 与 `NativeIndexSmoke` 本机服务已关闭。
- 文档/状态守卫通过；15 向文档、64 向状态探针均符合预期并逐字节恢复。
  blocked 恢复点正例通过，缺少对应阻塞条目的反例准确判 J7。
  冷恢复明确输出 `V2.R4.2` 为 blocked，只可解决权限/输入门，不得开始受限执行。
  观察摘要与控制面前后 hash：`native-index-control-checks-20261003.json`；
  完整后台 stdout 未形成可恢复工件，不把摘要冒充原始日志。
- state 已记录 R6.4 done；唯一下一任务为 R4.2，保持 blocked。项目 Goal 不标完成，
  不伪造系统 paused。README 已同步本机存储行为。
- 临时交接文件：`%TEMP%/amz-listing-kit-session-handoff-20261003.md`；
  持久恢复仍从 `uv run --locked python tools/refactor_resume.py` 与唯一 state 开始。
- 无真实模型/素材外发、无新依赖、无 Git 提交/推送、无部署、无 V1 删除。

## 7. 执行复盘：验证服务交付，不代替交付

用户指出验证与控制面投入偏重，要求积累教训。现有记录支持定性判断：
本地基础治理和证据体系已有大量产物，但统一配置、BYOK、第二真实 Adapter、
生成执行收敛及最终工作台仍未交付；没有完整工时统计，不推断浪费比例。
数据/OCC/包完整性与真实运行验证仍必要，问题是重复范围和优先级，不是取消验收。

后续执行约束（经验与用户偏好，不替代计划、任务依赖或权限规则）：

1. **以用户可见结果开工和汇报。** 每个切片先写清用户将能完成什么，
   同一切片实现并证明这条路径；测试数、报告数、探针数不等于产品完成度。
2. **验证按风险和变更边界选择。** 优先复用现有行为判据，实际运行改变的路径；
   保留数据不丢、OCC、秘密隔离、Unknown 不重提等关键不变量。
   全量回归安排在计划规定的验收节点或确有跨切片影响时，不因记忆不全重复已成立的检查。
3. **失败保留，假设驱动。** 出现失败先区分产品故障与验证脚本错误，定位后再验证改变；
   不靠重跑洗绿，不用一批绿样本证明历史故障根因已闭合。
4. **控制面只修阻断真实工作的缺口。** 状态/权限/恢复路由确有矛盾时做最小修复，
   不主动扩建验证框架，不把维护流程本身排成一条持续吞噬产品施工的主线。
5. **权限门限定到受限动作。** 预算/凭据缺失不能泛化为所有离线工作都禁止；
   只继续已授权且现有计划前置成立的切片。需要调整依赖时显式处理，不偷越 Gate。
6. **证据与文档保持最小可恢复。** 报告引用已有原始证据，记录结论、限制与准确下一动作；
   不复制多套状态，不反复写同一“不算完成”的说明。报告不能替代功能实现。
7. **收尾不重新开工。** 用户要求结束后，只完成在跑检查、保存恢复点并释放本轮资源；
   不借复盘再开施工。记忆中的阶段/任务快照可能过期，恢复只读仓库 state 与真实 Goal。

本次只追加复盘并校正长期记忆；没有降低 RC01–RC20、人审、数据安全或供应商调用门禁，
也没有调整任务依赖、删除测试、新增验证框架或继续产品施工。

