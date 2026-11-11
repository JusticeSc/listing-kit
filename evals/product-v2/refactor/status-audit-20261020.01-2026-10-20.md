<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/status-audit-20261020.md -->
# 当前状态审计与后续收口规划（2026-10-20）
[返回 status-audit-20261020.md](status-audit-20261020.md)

# 当前状态审计与后续收口规划（2026-10-20）

> NOT-AUTHORITY：本报告是时点审计证据，不发布权限、Goal生命周期或另一份执行状态。当前门与唯一恢复点只取 `_working/amz-listing-kit-product-v2/state.md`，正式安排取计划§17.13。本轮用户要求审计、确定状态、规划并评估过度测试；未据此恢复产品施工、模型调用或远程写入。

## 结论

项目不是待重做的基线，也不是只差三张缩放截图。当前产品代码已经受保护合并并发布，真实项目、五张采用图与两包均存在，最终离线两轮确实运行；但信息图的普通决定与实际人工稿/像素冲突，程序稿重新准备保留返工血缘的缺陷仍在，当前最终图组的完整品质验收和原生浏览器缩放尚未闭合。原生Goal本轮实际get为同一 `15ab22bf3386b9cf / active`，只读恢复输出 `V2.R5.1 / blocked`；没有标完成。

之前“其余全部验收已成立、只剩缩放”的聊天结论撤回。它把文件/案例盘点、有限回归和完整产品验收混为一谈。反过来，也不撤销已经合格的工程、两轮、发布或恢复证据。

## 1. 当前身份与保全资产

本轮实时观察与原字节计算在 `_stage-amz-control/status-audit-20261020/observations.json`；修改state/计划前的原字节在同目录 `authority-before.zip`。

| 对象 | 本轮直接观察 | 边界 |
|---|---|---|
| 源码 | 本地 `0c986f4647271c070926724d3007d205e1010495`，分支 docs/ui-matrix-evidence-20261020；远程main `97938457881ae4e25f5d5f1fa6085a641d4d9871`，PR #25已合并 | 本地落后该合并提交1个；审计开始时staged/unstaged均0，另有139项未跟踪过程材料，未清理或混入提交 |
| 实际服务 | tag `amz-listing-kit:3195192e4a1d29e374ea6d15fa8b4c7256dd42bf`，image `sha256:4abc01be655c9554534bb2804bcd60f711716a37e89c5ae649c351b5604b29cd`，healthy | 不是把main HEAD当作服务image；#22–#25是后续文档/证据提交 |
| 镜像内指纹 | runtime `48002dc42f054e4d90d1699ed5844a85a464fd3f792fc12719f8e9d671350714`，public config `652b120166ae07d8d3e89d1fbb53c414272d243701a4fb27cd0cc22feab3ced2`；95运行文件/71实际服务资产相等；default trial closed | 在实际容器内执行既有只读fingerprint，不是本机目录；HTTPS health通过正常证书校验 |
| 发布现场 | 无开放 `~/.config/amz-listing-kit/deploy-transaction.env`，无previous应用容器；现有服务及TLS容器运行 | 未发起新deploy/rollback/finalize |
| 实时保护 | main protected；strict/enforce_admins=true，禁force push，两项required上下文，审批数0 | 零强制人审不等于独立工程审查不存在；本轮未合并任何PR |
| 完整项目包 | `b19-project-post-suite.zip`：39,555,718B，sha256 `f2be0aa7a6e62158e0daecd18e262b7096e716b722a8beae45d0f35964e11b15`；340文档/28资产/369成员 | 本轮重算CRC和28资产实际sha/字节全部相符；包内用户数据未改 |
| 交付包 | `b19-delivery-final.zip`：5,817,832B，sha256 `6252990e55b28b847d21af2d54a7ea94330b2237389a96365b90e2bfdd69efc5`，五图逐成员sha/字节相符 | 文件/身份完整不等于品质合格或普通决定已被消费 |

两包和原五图均在 `_stage-amz-control/staleness-diagnosis-20261020/` 下。没有重生成、重新抓图或以审计副本替换正式采用。

## 2. 对完整目标的证据判断

| 目标 | 可保留的直接证据 | 尚未成立或适用边界 |
|---|---|---|
| 普通决定与程序Prompt | 当前五图main/scene/size/detail分别冻结系统稿v16/v17/v17/v13；原PR18及后续领域/消费者证据复用 | info是人工全文v19，不是程序稿；下述不印文字决定与实际稿/像素冲突，不能签普通决定驱动 |
| 确认/生成/返工事务 | 已记录的正式页面/请求及当前离线回归保留原断言范围，不重复付费链 | `prompts.prepare()`重新准备未保留返工血缘；不能用“回归全绿”覆盖这个未测到的状态转换 |
| 两Adapter×两模式 | 10-15四例都有真实出站、原返回像素和v2.4.1/capability3身份；两image Adapter源码在PR18后未改。新主图有Qwen原照→候选编辑真实来源，b19有当前原照输入 | 旧四例不是当前五图，部分旧结果本来就因错字未采用。当前pricing新增不等于协议变化；不预排额外Ark付费重跑。若后续确实改变有效输入协议/序列化，才补对应真调用 |
| 四段UI/人因 | 当前宽度矩阵与原英文警告可逆因果资产成立；窄屏选择器、取消回焦和键盘切段等有记录 | 原生125%/200%仍无合格证据；已试无头方法失败不证明所有无头方法普遍不可行。不再循环尝试同类方法 |
| 五用途真实成品 | 最终五条采用身份及对应像素存在；main/scene/size有b16/b17按sha的接受/拒绝记录 | 旧five-adopted-pixel-proof的五个sha与当前五个全部不同；detail/info缺原判据的验收记录。两名审计上下文已直接观察当前像素，但不以“未见明显问题”代替逐条合格判断，也不代签C15/C17 |
| 当前格式/两包恢复 | b19记录340文档/28资产导入；实际Blob摘要；再导出369成员仅exported_at不同。线上文档payload/资产元数据比较及实际ZIP哈希核对成立 | local reload_stable仅比较文档keys；online SNAPSHOT资产只投影元数据。不能单拿这些布尔宣称刷新后全部Blob原字节已逐条核。后续换图重出包时在同一次必要恢复中核实际字节，不另建平台/重做压力测试 |
| 最终离线回归 | `v2.7.1-regression-20261020-125146-final.json`：head48bfe17干净、两轮各50条、无problems、同结果指纹290ee1bd…；合并树与3195192一致。该JSON在origin/main真实存在（337,999B） | 只证明该候选的离线执行集合；不证明像素、人因、收费或本来未覆盖的血缘行为。后续文档HEAD变化不使产品证据全失效；实际消费者修复后须在最终新候选重做一次规定两轮 |
| 发布与同origin恢复 | PR21实际事务发布到finalize；本轮live指纹与发布工件相等；旧image部署/回退及线上两包/采用记录可复用 | 旧image7fdb…与当前image不同，但两者runtime同为48002…；不夸大为不同记录格式间迁移证明。新格式/新数据保全仍须按其实际变更核后置，不因容器healthy就签完 |

