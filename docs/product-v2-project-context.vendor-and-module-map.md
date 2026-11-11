<!-- 拆分件：vendor、目录与模块职责 -->
> [product-v2-project-context.md](product-v2-project-context.md) · CONTROL-STATUS: current · AUTHORITY: project-context
> 原文第 226–290 行 · [前片](product-v2-project-context.dependencies-frontend-tools.md) · [后片](product-v2-project-context.quality-and-routing.md)

<!-- 续接：本片承接 4.2 的 vendor 登记；本标记与续接标题在重组时移除。 -->
### 4.2 依赖与 vendor 登记（续：vendor）


<!-- vendor-registry:begin -->
| 文件 | 版本/来源 | 用途 | 引入决策 |
|---|---|---|---|
| fflate.browser.js | fflate 0.8.3（npm `esm/browser.js`，自包含 ESM，90,922B，sha256 `B7CA4450B19559A1D50EB381ADCEE94B82449674BE4CD17789D9BEBA7E6122A1`） | 浏览器 ZIP 读写（项目包导入导出） | SEL-008（2026-09-30 定，同批落地）；MIT |
| fflate.browser.d.ts | 自研类型边界（随 `fflate.browser.js` 同目录，仅 `zipSync/unzipSync` 两入口及所用选项形状） | TypeScript checkJs/noEmit 下 `storage/zip.js` 的 vendor 导入类型（不进运行时） | SEL-021 开发期检查；随库文件同目录校验，不改第三方实现 |
| fflate.LICENSE.txt | fflate 0.8.3 MIT 许可证原文（1,069B，sha256 `0A1DF3A083D0C010560AA342E87959C8C1070E6FD54545741F083F22D0C8B551`） | 第三方许可证随附 | SEL-008；与库文件同批校验 |
| axe-core.min.js | axe-core 4.13.0（npm `axe.min.js`，IIFE 单文件，580,491B，sha256 `C24F097BD2F451D4F933E8BC7D8D539F8672A2EBCB5CC9F9F3EEC8CA9470A0C1`） | 可访问性扫描（测试侧注入正式入口页面，不进产品运行时） | SEL-013（2026-10-01 定，同批落地）；MPL-2.0 |
| axe-core.LICENSE.txt | axe-core 4.13.0 MPL-2.0 许可证索引；按下列顺序拼接还原原文（15,921B，sha256 `AF175B9D96EE93C21A036152E1B905B0B95304D4AE8C2C921C7609100BA8DF7E`） | 第三方许可证随附 | SEL-013；与库文件同批校验 |
| axe-core.LICENSE.01-definitions-grants-and-responsibilities.txt | 许可证原文第一部分（8,974B，sha256 `48E0812931515DAF9A157F165501B3D6684228EF7033847C64AD423AA6D50DDF`） | 定义、授权与责任 | 与第二部分顺序拼接校验原文 |
| axe-core.LICENSE.02-compliance-and-notices.txt | 许可证原文第二部分（6,947B，sha256 `775868AF49BC2915F7AF28C9C07FF5E45F031FCF49224386E2C5386AFEDB7FA4`） | 合规与声明 | 与第一部分顺序拼接校验原文 |
<!-- vendor-registry:end -->
SEL-008 已落地（2026-09-30）：`storage/zip.js` 退化为薄适配器，结构解析与解压委托
fflate，只保留产品上限/错误码与逐条 CRC32 完整性校验（fflate 自身不校验 CRC32）。
升级上游时重跑包合同与 V2.1.3 往返验证，并更新本表哈希；证据
`evals/product-v2/sel008-fflate-vendoring-20260930.txt`。

## 5. 目标目录地图

```text
amz-listing-kit/
├─ app/
│  ├─ server.py                         # 正式服务入口：唯一 V2（旧 --legacy-v1/V1/Mock 可执行入口已随 main 基线 P1 退出）
│  ├─ product_v2_server.py              # 无状态HTTP装配：静态/health/capabilities、文字/商品图文 semantic/analyze、生图、单图及整套复核
│  └─ product_v2/                       # V2 前端静态资源；domain/prompt.js 是 Prompt 编译与人工编辑唯一权威（V2.3.4 / V2.3.6）、domain/confirm.js 是生成前确认唯一权威（V2.3.5）、domain/review.js 是确定性校验与 VLM 复核映射（规则注册表 / ReviewReport）唯一权威（V2.5.1 / V2.5.2）、domain/compare.js 是候选比较与审核清单排序的视图模型唯一权威（先看顺序仍取自 review.js 的 REVIEW_SEVERITY_ORDER，V2.5.3）、domain/rework.js 是九类返工问题与 ReworkDirective 返工指令合同的唯一权威（比较区保持只读，V2.5.4）、domain/selection.js 是人工选择（SelectionRecord/SelectionSet、采用/改选/取消与失效判断）唯一权威（V2.6.1）；domain/attempt.ts 与 domain/config-export.ts 是生成 Attempt 与可分享配置的唯一手工源码（同名 `.js` 是 `npm run build:frontend` 产物，V2.R7.5）；vendor/ 已 vendored fflate 0.8.3（SEL-008）
├─ src/
│  ├─ providers/                       # 分用途业务合同、registry/credentials/outbound、有限协议Adapter；v2_langchain_chat共享已批准图文传输；v2_errors.py为错误词表
│  └─ validators/                       # 未启用：确定性校验的唯一落点是 app/product_v2/domain/review.js（V2.5.1），本目录不建第二份
├─ config/
│  └─ product-v2/                      # providers.json为有限配置权威；平台/模板/规则继续集中前端domain，不迁出第二份表
├─ docs/
│  ├─ INDEX.md                          # 文档身份和读取路由
│  ├─ product-v2-project-context.md     # 本文件
│  └─ product-v2-refactor-plan.md        # 当前目标/任务；旧 goal-and-implementation-plan 是历史基线
├─ _working/amz-listing-kit-product-v2/
│  └─ state.md                          # 唯一执行状态
├─ evals/product-v2/                   # 时间点证据，不是规约或进度权威
├─ .github/workflows/ci-cd.yml           # PR/push CI；main Docker CD
├─ Dockerfile                            # 只打包 Product V2 正式运行入口
└─ tools/                               # 控制面、契约、浏览器和回归验证入口；v2_test_server.py 复用产品处理器 + fake provider
```

2026-10-12本地清退仅覆盖旧Mock/demo可执行闭包及其过期bootstrap验证，不是完整V1日落或线上发布。历史JSON、许可、用户资产与证据保留；精确原字节/退役清单见 `_stage-amz-control/next-version-design-20261012/baseline/`，当前局部进度见 `discussion.md`。本轮 P1 已按真实消费者闭包完成 V1/旧槽卡生产链删除（177 项，见 `main-baseline-execution-20261017/v1-retirement/deletion-record.json`），六类消费者同包迁移；用户原件、许可、失败/账本与选中恢复包保留。

新增目录前先判断它属于实现、目标、状态还是证据；不能归类的目录先不建。目录地图描述的是目标落点，尚未存在的均标为“目标”，不能据此声称已经实现。

### 5.1 业务模块与承接边界

业务合同只在计划§14；本节规定实现落点，不复制需求矩阵或另立状态机。下表是**本轮目标职责**，不是现有代码全部满足这些边界的声明。Module所有权、具体Interface、生命周期/事务、重复治理、测试和历史策略的目标详细设计唯一在 `product-v2-refactor-design.md`；复用现有domain，不另建万能facade、独立人工数据模型或公共合同大文件。

| 职责 | 既有落点 | 接口/状态边界 |
|---|---|---|
| 资料与事实 | 现有project-inputs、semantic-analysis；domain/intake、slots、brief；repository | 人工与模型走同一领域动作，来源/权限/提议/确认与只读sources分开；仍有的UI/草稿回调接缝按详细设计收口，不因文件存在认定已全部完成 |
| 图片任务与需求 | domain/suite-plan、specs | 用途/模板及事实/参考图依赖单一注册；可保存不完整任务，逐Shot派生就绪/缺项，UI和Python不重建表 |
| 本地准备与确认 | prompts、generation；domain/prompt、confirm、invalidation | prompts拥有编译/人工文本/历史，generation拥有摘要授权及消费；强耦合授权合入generation，不保留独立转发层 |
| 会话与存储 | session；storage/repository及db | ready/身份/生命周期/OCC、文档版本、追加观察及Blob事务；异步回调归属原快照，事务不await网络 |
| 生成执行 | generation；domain/attempt、batch、rework、candidate | 单张/批量/返工同一执行顺序；冻结登记先于外发，partial/Unknown保持原身份，不在UI拼第二路径 |
| 比较与采用 | selection-adoption；domain/compare、selection、review | 单图确定性/显式AI报告与采用归同一所有者，generation只提供候选/动作投影；查看/对照归视图，Selection只由人改变 |
| 交付与恢复 | review-delivery；domain/suite-review、export-gate；storage/package、transfer及ZIP | 整套报告/交付门/记录/构包由业务Module完成；一致快照与原动作追溯按详细设计，不由UI组manifest |
| 模型边界 | product_v2_server；providers/semantic、review、suite_review、image及registry/credentials/outbound/langchain_chat | 无业务落盘；请求级有限有效配置/凭据，共享传输不共享错误业务schema。商品看图理解需要独立提议合同，不复用要求candidate的复核请求 |
| UI投影 | workspace、现有input/generation/compare/delivery-view、index、ui/stage-shell及styles | 装配/生命周期与业务投影，不复制owner命令。已成立的单向装配不重做；当前实际差量按源码、state与关联Issue判断，不把历史§11.5的callback/report清单当现行施工任务 |

Interface是可调用的业务动作及可渲染快照，不等于HTTP或额外转发层；Seam是可替换协议/凭据/传输/存储等边界。fake仅替外部模型，保持正式装配和领域消费，不能以fake出图证明真模型理解/忠实度。

基础配置与现有三用途消费者、商品图文Adapter均已有实现；范围匹配的行为/秘密/真实能力证据各自判断，不据静态接线宣称全部验收。单一模块/组合设计取详细设计§13及仍适用的§2–4；历史§11.5仅追溯未解决且仍有实际证据的差量，不从旧清单重做已完成owner。正式依赖/验收取计划，当前前沿/权限取state，具体改造/验收取Issue #10及关联工单。


