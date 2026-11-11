<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/storage-contract-review-20261003.md -->
# V2.R6.4 存储与合同测量复访（2026-10-03）
[返回 storage-contract-review-20261003.md](storage-contract-review-20261003.md)

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

