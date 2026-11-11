<!-- 拆分件：docs/INDEX.md · 登记：项目入口与早期记录 -->
> [文档入口](../INDEX.md) · [入口](../INDEX.md) · [下一页](state-and-history.md)
> 身份和权威归父文档；初始拆分原件为公开 main 第 35–55 行，已退役条目改从恢复登记查询。

## 2. 登记表

> 受管范围：根目录（`README.md`、`AGENTS.md`）+ `docs/` + `_working/` 下的在场 `.md` 与真实状态 `state.yaml`——逻辑文档在本表登记，分片由父文档在拆分登记中认领。
> 非生成文档顶部必须有与登记一致的 `CONTROL-STATUS`；分片继承父文档身份，机器状态由同目录状态页认领（`tools/check_docs.py` 双向比对 + 唯一权威校验）。
> `evals/` 与 `_stage-amz-control/` 是证据与快照产物，不参与“哪一份有效”的登记。

| 路径 | 世代 | 管辖事实 | 状态 | 说明 |
|---|---|---|---|---|
| `README.md` | Product V2 | `实现` | `current` | 当前实现的人读入口：唯一V2、锁定构建/启动/验证及同版本恢复；main/分支/发布身份只取state和实际PR证据 |
| `AGENTS.md` | Product V2 | `项目规则` | `current` | Agent 工作规则与选型门禁（Reuse-first）的唯一权威；目标、技术栈、状态分别链接到各自权威，不复制正文 |
| `_working/amz-listing-kit-product-v1/state.md` | Product V1 | `历史证据` | `superseded` | 被演示产品状态取代，其原件从 `config/retired-documents.json` 查询；保留上一轮执行位置，不据以继续开工 |
| `_working/amz-listing-kit-requirements/state.md` | 演示产品需求发现 | `历史证据` | `superseded` | 被演示产品状态取代，其原件从 `config/retired-documents.json` 查询；保留需求阶段完成轨迹 |
| `docs/product-v2-project-context.md` | Product V2 | `架构设计` | `current` | Product V2 项目身份、运行边界、数据所有权、技术栈、目录地图和质量门槛的唯一上下文入口 |
| `docs/product-v2-refactor-plan.md` | Product V2定向重构 | `产品目标` | `current` | §2.1保留真实原生Goal观察全文；§17.13最新完整交付授权/差量；§17.2–17.5执行包与复用合同；§6/§9/§10正式依赖和最终准出不被局部工单完成替代 |
| `docs/product-v2-refactor-design.md` | Product V2联合结构重构 | `架构设计` | `current` | 当前§13普通决定/两模式及视觉简报/人因验收；§12仅作当前路由，§10–11旧算法/实施差距按未变前提复用。规格不冒称实现、Goal或当前权限 |
