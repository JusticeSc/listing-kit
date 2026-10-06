# 详细结构设计：本轮交付与限定证据

> NOT-AUTHORITY：2026-10-06时点证据，不发布后续进度/目标/权限；目标设计取 `docs/product-v2-refactor-design.md`，进度取state。

## 1. 用户要求与执行范围

用户要求“做好详细设计”；此前明确结构重构必须主动处理项目代码/设计问题、重复冗余、历史材料和脆弱测试，不应等用户逐项指出。本轮仅设计及文档/恢复一致性检查，不解除停止施工门，不改Goal、任务依赖、预算、已确认业务权限、真人/V1外部门。

未进行产品源码/配置/CI写入、历史材料移动/删除、产品启动/浏览器操作、编译/类型诊断/产品回归、模型调用、提交/推送或发布。三项并行设计代理仅给替代Interface和风险，不执行任何实现/运行检查；其建议由父代理判断，不作为现状或验收证据。

## 2. 设计依据与处理

- 原现场失败取 `generation-module-20261005-formal.md` §停工节：新建项目保存后打开报 `suiteReports is not defined`，工作区隐藏；本轮不重跑确认已报告失败。
- 本轮此前的只读原生compiler配置/transpile字节比较：domain/attempt、domain/config-export、semantic-analysis、session、model-settings五个已登记TS对应JS相符；generation不符；prompts/authorization/selection-adoption/review-delivery四个新TS在compiler program内但不在emit/freshness名单，prompts.js不存在，另三JS不是对应TS生成字节。不是类型检查或本轮修复证据。
- 已读现有state、计划、context、AGENTS、workspace装配/直读/reset、新Module Interface、generation实际登记/外发/授权顺序、repository单文档OCC与包导出分散读取、现有共享fixture/源码钉/HEAD裁剪生成器、既有历史清理工具与归档摘要。
- 采用显式所有者+业务自然收口，而非万能dispatch/新的总命令facade。设计确定授权合并generation、输入迁owner、单图报告与采用收口、整套交付自管构包；完整Interface、依赖DAG、生命周期、线性化/事务fence、六用户路径及反例均进入目标设计。
- 冻结不证明当前性；单页Set不证明跨标签授权消费；单文档原子save不证明整包一致快照；类型program不证明实际emit/browser字节一致。三备选中相应不足没有原样采用。
- 原任务卡与§15.4承接详细设计及结构准出，AGENTS增加主动治理规则；INDEX登记与context只作路由/职责概要。state仅加设计证据与停工备注，保留唯一V2.R5.1 blocked、历史Goal观察和未完成运行失败，未推进工程进度。

## 3. 事前原字节与不变合同

五份权威文件事前原字节副本及SHA256：工作区根 `_stage-amz-control/detailed-design-2026-10-06T03-00-50-972Z/snapshot-manifest.json`；该目录不在产品仓库内。新增设计此前不存在。事后各文件字节hash与Goal/任务/恢复不变项记录在同目录 `design-result-manifest.json`，不以reader截断文本构造文件hash。

原字节及完整节比较已确认Goal §2.1保持SHA256 `6677a6803003f0894dd522bdd7102b53ca30c866532ff48fdc79e4b148d7c495`；原27任务/8阶段/依赖表/RC、绑定ID/最近真实系统观察、全部任务与阶段状态、下一动作和停工blocker不变。原生比较捕获完整依赖节2970字符和RC节1590字符；最初临时选择器将行尾误当节尾，已纠正为全文末尾并验证节内末行存在，不能用初版截短比较作证明。这里只验证仓库不变合同；系统Goal工具此前返回Unknown tool，不能把历史active读数说成本轮实时Goal读数。

## 4. 本轮验证

全部设计/权威路由写完后串行实际执行，限定结果见 `detailed-refactor-design-20261006-checks.json`：

| 检查 | 观察结果 | 证明范围 |
|---|---|---|
| `uv run --locked python tools/check_docs.py --no-run` | 退出0；登记62份与实际62份一致；9.66秒 | 路由/权威/选型映射一致；明确不证明文档中的运行命令 |
| `uv run --locked python tools/refactor_resume.py` | 退出0；8阶段/27任务；2.91秒；唯一V2.R5.1 blocked，打印停工禁令和更新任务卡 | 实际恢复入口消费新设计路由仍安全停在原工程前沿；不查询实时系统Goal |
| 原生完整文件hash及完整节/字段比较 | manifest中不变项均true | Goal/任务依赖/RC/全部状态/停工/历史绑定未被设计轮改写；六份结果文档的前后/新增字节指纹可追溯 |

没有运行产品、编译/类型诊断、行为测试、付费调用或最终两轮来“验证”设计。恢复入口内已检查登记和state，不另重复同一状态守卫/全套探针；工程状态与依赖未改变，没有以设计名义推进任务。

设计内容覆盖核对：详细设计§1给出比较及选择，§2–4给出所有权/Interface/事务/生命周期，§5给出用户路径，§6–8给出重复冗余/测试/历史材料处理，§9映射原任务施工包、失败回退与六项结构准出。它们是设计产物，尚未获得工程行为证明。

## 5. 证明范围

本轮可交付的是可施工目标设计、原任务承接/治理准出、停工恢复与权威路由一致。未证明产品修复、接口实现、跨标签事务、新JS一致、完整人工/辅助路径、最终两轮、真实CI/HTTPS/两不同版本回退；这些不能由本轮文档检查冒充。现场中间态与首次失败继续承接原任务。
