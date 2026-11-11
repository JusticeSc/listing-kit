<!-- 拆分件 02/03 · 父文档 evals/product-v2/refactor/audit-after-stop-20261008.md -->
# 4. 六项Goal准出映射：已有资产与仍缺证明
[返回 audit-after-stop-20261008.md](audit-after-stop-20261008.md)

## 4. 六项Goal准出映射：已有资产与仍缺证明

| Goal条件 | 可复用的直接证据 | 当前缺口与裁决 |
|---|---|---|
| SC1 人工/辅助完整任务 | manual.json：空页面人工确认/一次提交/返工/采用/无AI两包/同origin重启；原两Adapter真链与2026-10-05原图2239735B真实图文理解子步 | **partial**：辅助任务没有连续走到原生两包；人工链Fake不证明真图忠实度，初始批次全请求轨迹明确缺失 |
| SC2 三用途BYOK/按需AI/秘密 | packet08真实页面输入/正式消费者出站、合法图缺key、真实旧schema拒绝已修；主路径与live default_trial=closed成立 | **partial**：S5长度oracle/压缩ZIP扫描/缺失表面不能证明精确用途key与完整秘密隔离；不是产品泄漏结论 |
| SC3 事务/恢复/结构与已知缺陷 | 五owner/四视图/既有事务及main CI相应行为、HTTP未读正文修复、settings草稿/容量/停止/报告消费差量保留 | **partial**：RC19因果仍缺；4_2加入TimeoutError及同action/task DOM+IDB接受规则不是受控时序因果证明；结构六项需范围匹配综合准出 |
| SC4 模拟真人/视觉/键盘 | manual/zoom证据：真实页面、真实125%/200%缩放、1440/1366/390关键可达、键盘导出 | **partial**：辅助分支完整走查未证，不能拿截图文件存在代读图；C17/C15独立真人仍未发生 |
| SC5 类型/两轮/清理 | 已改变集合types/generated/Node/CI、p11close2的当批44×2、旧实现材料可恢复 | **partial**：R7.3 WIP未闭合，最后消费者/V1改动后同源码候选两轮及最终指纹缺；信号hash不是源码hash |
| SC6 当前候选/发布/回退 | 本次真实Docker/不同image markerA-B、镜像origin页面、同origin数据恢复、HTTPS/指纹/finalize与8份live字节一致 | **partial**：R7.4最终冻结未发生；当前main无强制保护、PR无review；既定回退机制可复用，不扩大为必须两份历史产品版本 |

RC19最新网络诊断 `asset-continuation-20261008-rc19.json`：600次/34800请求未捕获拒连，464740事件未出现对应refused。这只说明本次未触发，不建立因果、不关闭RC19。不能再以同配置连续绿、加等待或另一机制放行。

## 5. Standards：停工WIP与恢复纪律

### S1（高）：用户停工门没有落入唯一恢复入口

审计开始state头仍“继续吧”，R5.1 active、blockers=[]；实际 `refactor_resume.py` 输出active/R5.1，没有停工提示。工作区外handoff不能替代INDEX指向的state。本轮只将R5.1改blocked，填任务前缀的停止/额度/缺证阻塞并指向本审计；系统Goal仍active，不伪造paused。Phase5保留其历史未完成active归属，不作为施工许可。

### S2（高）：WIP的历史缺证降级不能仅补参数收尾

`15faa65:tools/check_project_state.py`新增 `_evidence_ok(..., superseded=False)`，两个v2调用点未传，故已知历史J6红仍在；本轮不重跑确认。reviewer按15个done任务的两类指针静态复算为30条J6，不是handoff写的10条，静态复算不冒充本轮执行结果。即使接线，按superseded给**任意**missing降note会掩盖与V1日落无关的历史证据丢失。应只认可有精确退休清单/原commit或归档hash的路径；当前证据继续严格报错、历史意外缺失仍报错，复用现有反向探针。不为绿灯重写历史或添加通用兼容层。

### S3（高）：保存现场时违反精确纳入规则，旧handoff的文件状态不准确

AGENTS:103–105禁止 `git add -A`，只晋级选中最小证据。停工保存15faa65实际用了add-A，将9份快照/恢复文件也纳入WIP；126文件不是126产品变更。切回main会移除这些分支专有路径，故旧handoff“快照仍untracked/当前路径可用”不准确。材料未丢失：Git blob已验证ZIP hash `4007b9b1…`、manifest hash `a6269682…`；本轮原生字节hash另证当前main的 `_stage-amz-control/asset-continuation-20261008T054352Z/data/manual-project.zip` 与该代表包完全相同，重载荷并非仅在WIP。main上的R7.3探针默认数据输入/专有材料路径不可达，探针脚本本身仍在工作区根 `_working/`；后续精确提取/恢复，不checkout/reset覆盖本轮未提交state，不以当前路径缺失断言原件丢失。reviewer核对114个删除文件均匹配删前manifest/hash、133个Python文件静态无指向删除集的import；这是静态依赖审计，不替代删后smoke。实际删掉23个 `verify_product_v1_*`，本轮git集合计数23，不是handoff的31。

### S4（中）：R7.3数据探针仅是有限导入/项目包往返

工作区根 `_working/_probe_r73_data_recovery.py:158–193,200–230`检查项目身份/名称/revision、文档/资产数量、资产名字/字节hash与项目ZIP成员。没有逐条文档payload/采用/current比较，没有实际返工，没有交付ZIP轨迹，也没有hash与manifest完整合同逐项核对。旧handoff将它称为“打开/返工/导出可直接复用判据”过宽。保留其项目包/Blob子步；R7.3还需复用原6_3/人工链证明真实返工和交付，不新造验证平台。

### S5（高）：BYOK旧空证已修前置，但“精确用途/完整包无泄漏”仍有证明缺口

`tools/verify_v2_packet08_settings_vision.py:61–65`三用途哨兵长度相同；`:524–530`捕获请求即把key缩为长度，`:672–677,717–722,741–746,761–766`只比较该长度，无法区分同长度的错误key或用途错换。`:786–793`直接把压缩ZIP原字节decode扫字符串，没有逐成员解压，也没有扫描localStorage、交付ZIP或服务端日志；`:148–150`的IDB dump将Blob替换为大小占位。长度/压缩字节扫阴性不能覆盖设计§11.5.3:535的精确用途key与完整秘密隔离合同。

真实页面键入key、正式消费者外发、合法图片缺key与旧格式实际上传拒绝已经补上，保留这些成果；不能又把它们称为全部空证，也不能由缺证推断产品实际泄漏。后续在同一现有入口用内存中精确比较或非秘密哨兵等值布尔后置，证据不保存真实key/hash；独立读完整localStorage/两包解压成员/相关日志，补足具体缺的表面，不购买模型调用或新增安全平台。

