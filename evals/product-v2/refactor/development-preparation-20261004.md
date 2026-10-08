# 2026-10-04 正式开发前准备记录

> NOT-AUTHORITY: point-in-time evidence。目标/合同只在原计划，进度只在current state；本记录不发布另一套准备计划，不证明产品已实现或可发布。

## 1. 请求与已确认选择

用户要求：“开始完善修订优化，做好正式开发前的所有准备，包括拟创建的goal文本，有什么问题或需要澄清的及时向我提出”。本次只修订既有权威、拟创建正文和恢复记录；没有产品代码/配置/依赖/验证器/CI修改，没有供应商请求、付费、提交/推送/合并/部署，没有Goal创建或生命周期写入。

本次ask原选择：
- `next_delivery`：完整工程成品＋现有环境发布。
- `new_live_calls`：最多补3次图文／复核。问题明确：仍计入原累计≤5元，新增费用≤1元；语义/VLM上限4→6、总次数12→14，生图仍最多8次，不追加。
- `release_merge`：授权CI通过后代理合并。问题明确：满足现有审查/分支保护、不绕过、不强推。

以上为下一轮拟启动方案，不是本次执行许可；原文落点为计划§16.1，正式创建/开发仍待用户另行触发。

## 2. 本次变更与证明边界

修改六份既有权威：AGENTS、INDEX、plan、context、UI草案、state。计划r7清理§8.1失效施工顺序及§12.3重复施工表；新增§7.5需求修订后的done、§7.6缺陷准出、§7.7发布/回退合同；§16集中唯一拟创建Goal、用户选择及一次启动步骤。原§2.1及旧观察未改。

依赖修订：R4.3闭合共享配置/现有文字、生图、单图/整套复核及设置消费者；新商品图文理解由R6.1后续批次消费同边界。R6.2 Depends由R6.1改为R5.3，人工批次先提供输入证据，不等待R6.1后续图文整项done；G6和RC07仍要求全部消费者闭合，不减少最终验收。R6.1/R6.3跨批剩余条件未满足不得整项done。

修正已核对过时事实：CI已有VOLCENGINE_API_KEY→ARK_API_KEY接线（ci-cd.yml:175–177）；图像已有请求级BYOK（README/context及凭据合同）；verify_v2_2_3已登记CI离线入口（verification.json:128–133），登记不等于本次运行通过。

发布回退缺口仍存在：ci-cd.yml:278删除previous后，305–316才检查外部HTTPS且失败退出。本次只将完整发布事务/服务与数据恢复要求承接到R7.4，未修流水线、未验证远程回退。

UI仍draft。区分设计范围确认、工程浏览器验证与C17/C15真人门；不把本次文本当可点击原型、owner签署或新G2证据。state仍停在blocked R6.3，历史阶段/任务状态不冒充新验收；正式启动时依§7.5/§16.2重判受影响前沿，不提前改绑定或重置工程。

## 3. 实时Goal与拟创建正文

工具真实观察时刻：2026-10-04T05:44:31.524Z。原始结构化返回：

```json
{"text":"No active goal.","details":{"op":"get","goal":null,"remainingTokens":null,"completionBudgetReport":null}}
```

本次未创建Goal。下一轮唯一拟创建全文在 `docs/product-v2-refactor-plan.md` §16.3（不在本证据复制正文）。从文件原生字节解码提取text围栏并核对：
- 历史§2.1与事前快照正文逐字相同；SHA256 `3f9f1842d67d063fa9d8cfbbaf60eb5971fe24b46502c97455241ccac40d4607`。
- 拟创建正文SHA256 `6677a6803003f0894dd522bdd7102b53ca30c866532ff48fdc79e4b148d7c495`；JS字符串2698字符。该指纹不是已绑定系统Goal指纹。
- 第一次临时提取脚本因跨行正则错误报Missing objective；修正提取规则后完成比较，不涉及产品/文件修改，不把失败当作已通过。

## 4. 原字节快照及仓库边界

事前快照：`_stage-amz-control/development-preparation-20261004T053317Z/`，六份原始字节均与源文件完整SHA256一致，不使用reader截断文本重建。下表为本次六份权威修改后的指纹（证据自身不参与循环指纹）：

| 文件 | 改前SHA256 | 改后SHA256 |
|---|---|---|
| AGENTS.md | ecce9403dd75707c513d4b13cd52a7995ed331e670e89c217c61f07439875222 | 286f7e1593895faa0be09fa7760b50240c0a36635efd72a7d315abf6781598cd |
| docs/INDEX.md | d0bd8e4de532a7da97f6f7598e60b0a7818703820da54cfdc7c64c93ab3e335e | 88ab20a0e0aba1221bd06650c8b5b09e0326d94fb6d44ebbfca226714559c81c |
| docs/product-v2-refactor-plan.md | 68b26a72473d3287e848137341b4a24ab6e3a0efdf86e80fbb698de1cf82e8da | efe2d0d92d848434af55f7d6c68e617b23e4291b45da618bd0a1ac82825b6c23 |
| docs/product-v2-project-context.md | e793f0c8730b25d4db32edb0355e00636430a392c189462e04457668c133f77a | d3b77d3fdd7368fb90f35d8a11d6c376de253e2709918362900f6fbe6da5e102 |
| docs/product-v2-ui-contract.md | 3b47ec3c5c7355c158c2e4ad7713370d3ef09759fe98f655b0533bb2232f7411 | 1582b2d0c5e00da28f4dd7ac0c3d604ba654eb56275dce335b2aaf09ff447eb9 |
| _working/amz-listing-kit-product-v2/state.md | 036e73bdaaf3866e75ddd55ca990dd2fa1f98620dab44d808d9ef0eabc19b180 | 5aa7dc7f53a083333ffef44c256d9e8972ac17b0894c526f0bfed614eb49301b |

一次只读仓库基线查询返回：当前分支main，HEAD `aa24514082164f79f20a111c560670fb443b9a07`；staged 0、unstaged 6、untracked 57。该时点已包含本次文档修改和快照，不是原始干净基线，不证明未跟踪文件都属于本轮。未跟踪中含既有快照/原型/过程脚本/旧证据，未删除或纳入提交；不能用git add -A打包。本次原字节快照只覆盖文档，不冒充完整代码/产品数据恢复基线。

## 5. 准备验证

实际串行运行一次以下链路，整条命令退出码0、耗时152.33秒。没有逐编辑运行，也没有为了提高信心重复；依赖表改变，所以本次执行已有状态反向探针，不新增探针/验证器。

| 命令 | 实际结果 | 证明范围与限制 |
|---|---|---|
| `uv run --locked python tools/check_docs.py --no-run` | 全过；登记61/实际61，依赖/锁/vendor及14份模板映射一致 | 文档结构和静态规则；明确不证明文档中的产品/legacy命令本次运行 |
| `uv run --locked python tools/check_project_state.py` | J0–J10全过，5份工作记录 | 状态/计划/依赖/历史观察结构一致，不是当前系统Goal或新产品验收 |
| `uv run --locked python evals/probes/project_state.py` | 64向全部符合预期；脚本报告逐字节恢复state/临时证据并清理副本 | 现有状态规则的正反例，包括依赖、伪绑定/越权、blocked恢复；不证明新业务实现 |
| `uv run --locked python tools/refactor_resume.py` | PASS，8阶段/26任务；next=blocked R6.3，任务卡472行，明确只准处理准备/启动门 | 实际只读恢复入口仍禁止受限执行，blocker指向计划§16；打印历史active/required且明确不查系统Goal，不覆盖§3实时No active goal |

冷恢复原Goal正文SHA256仍为 `3f9f1842d67d063fa9d8cfbbaf60eb5971fe24b46502c97455241ccac40d4607`，与事前快照一致。拟创建正文指纹见§3，不使用旧观察绑定新正文。

本轮规约/下一轮方案/目标草案及恢复限制的准备交付已核对；真实创建、代码/数据运行基线、模型调用、UI实际路径、图片质量、发布和真人验收未发生，不能称工程已交付、可发布或Goal完成。没有跑产品回归、类型全量/存储压力、真实模型或线上探测，没有提交。

## 6. 必须在正式启动时完成的实时事项

实时Goal创建/绑定、新正文及观察同步、受影响任务/Gate一次重判、第一次产品写入前同版本代码/配置/代表项目ZIP实际恢复基线、原账本增量授权入账及凭据注入/价格/素材准入，只能在另行正式触发后按计划§16.2完成。本次不制造这些未来事实，也不把预算剩额当供应商余额。任一对应条件不可达保持精确未完成，继续其他已授权可达工作。
