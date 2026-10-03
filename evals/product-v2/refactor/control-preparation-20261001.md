# 重构计划准备与控制面校准 · 2026-10-01

NOT-AUTHORITY: point-in-time preparation evidence; not a plan, current state, Goal observation or product completion

## 本轮事实与权限

用户要求：详细实施计划落盘、控制面校准、拟创建Goal原文，下一任务不得依赖会话。用户已确认浏览器本地优先+Python网关、有限模型解耦、BYOK为主默认档受限试用、第二生图模型先评估、前端工程化及UI人体工程审计方向。

本轮没有创建或变更系统Goal，没有开始产品重构、执行UI审计、调用付费模型、上传素材、写远程Secrets、部署或Git提交/推送。实际模型与库/框架、预算/访问策略仍待对应任务门。

## 基线与校准原因

旧current state写V2.7.1 done、blockers=[]、next_action V2.7.3；用户后续报告了verify_v2_1_2间歇失败及两轮回归阻塞，且无带时间线失败样本。以用户报告为实际失败事实，不重跑来确认/否定；新state记录未闭合根因，由R1.2/R3.3承接，旧done不充当当前发布绿灯。

旧系统Goal最近实际仓库读数：01a0ca17-2179-7eb0-969a-af9c79c4d8ca，active@2026-10-01T14:22:19+08:00。本轮未重新读取系统状态，文档归档不改变生命周期；不得把它写成已经paused或complete。

修改前精确快照（工作区根相对路径）：
`_stage-amz-control/refactor-plan-2026-10-01T085723692Z/`。
旧state原始字节保存在该快照，仓库历史基线 `_working/amz-listing-kit-product-v2-baseline/state.md` 仅改本地身份/开放相位并移除历史下一动作；已完成证据与旧实际Goal读数保留。

## 本轮产物

- 唯一当前目标 `docs/product-v2-refactor-plan.md`：8阶段、26任务、逐卡输入/动作/输出/验收/失败回退、20项完成矩阵、UI场景/窗口/缩放/键盘、预算与人审门、唯一拟建Goal原文。
- context的SEL-014..017及旧选型复访：确认方向，不冒充具体库/第二模型或BYOK已实现。
- INDEX/AGENTS/README/UI合同路由切换；旧plan/state/走查任务书标历史，旧C15/C17没有被宣布通过。
- 唯一state为prepared：新Goal ID/实际读数为空，未绑定原因持久化，无active施工；R0校验后下一任务是R1.1 Goal核对/绑定。
- 控制守卫和反向探针增加prepared合法/非法情形；冷恢复入口 `tools/refactor_resume.py` 只读。

## 验证状态

首轮集成实际运行：文档静态守卫 rc=0；状态守卫 rc=0；修正后状态反向探针33向全部匹配，登记反向探针12向全部匹配，均逐字节还原；独立进程冷恢复 rc=0，读取8阶段/26任务、prepared/null Goal及R0.2卡。下面将记录完成R0.2、next切至R1.1之后的最终运行。


首次登记探针N因硬编码旧V2.5.5 current done事实退役后rc=0而失败；删除这条依赖旧任务身份/头文字的过时断言及其脚手架，不把历史任务塞回新state，不修改现有登记守卫规则。保留12条真实登记/双权威/依赖漂移负例。

首次状态探针F假设至少一阶段done而StopIteration；改为有done取done、否则首阶段构造缺证据负例。第二次AC把v2 Gate依赖搬进只接受任务引用的legacy形状，同时触发J6；修正legacy负例仅含合法任务引用，使它只因prepared身份触发J9。未放宽生产守卫，也未扩大探针允许tag集合。
## 限度
计划与准备控制完成不证明重构完成、UI改善、模型兼容、安全上线、人审通过或Goal已创建。文件本地持久化不等于已提交/CI可见；本轮没有提交权限执行，需未来精确纳入权威文件与选中证据。


## 最终状态上的真实运行

记录时间：2026-10-01T09:26:37.929Z。状态R0.1/R0.2及Phase0 done；prepared未绑定，下一动作V2.R1.1。

| 验证入口 | 实际结果 | 证明范围 |
|---|---|---|
| `uv run --locked python tools/check_docs.py --no-run` | rc=0；60份登记与实际相等、唯一产品目标/执行状态各1 | 静态文档登记/依赖/模板，不证明文档所有命令可运行 |
| `uv run --locked python tools/check_project_state.py` | rc=0；5份工作记录 | 当前prepared及历史身份、证据/依赖/时点规则 |
| `uv run --locked python evals/probes/project_state.py` | rc=0；33向各rc/tag与期望完全一致；逐字节恢复 | 合法prepared/active/paused与非法绑定/假读数/越门/未来时点等 |
| `uv run --locked python evals/probes/docs_index.py` | rc=0；12向各rc/消息与期望一致；逐字节恢复 | 登记漏项/幽灵/双头/权威缺失/依赖漂移等 |
| `tools/refactor_resume.py` 默认 / `--json` / `--goal-text`，各独立uv进程 | 各rc=0；8阶段/26任务、prepared/null Goal、V2.R1.1、卡片行245；14份控制文件前后SHA256全等 | 实际冷启动无需聊天变量；只读恢复，原文与JSON逐字一致 |
| 纯内存恢复负例smoke（没有创建测试文件或改变仓库） | 依赖环、重复任务（原守卫J6先拦截）、缺下一卡、Phase done而成员任务pending均拒绝；补丁释放后仍解析R1.1 | 恢复不会把不完整计划/假Gate作为下一动作依据；不增加永久源文本测试 |

Goal原文SHA256：`731d1ca284792c8aefcc97bfb69bc5734698c337bd0475f48d3177c5584815ea`；唯一源为计划§2.1（行31），不另存候选副本。默认冷读原始任务卡输出：

```text
[PASS] 冷恢复：8 阶段 / 26 任务；状态 prepared
目标：docs/product-v2-refactor-plan.md；状态：_working/amz-listing-kit-product-v2/state.md
唯一下一动作：V2.R1.1
任务卡：docs/product-v2-refactor-plan.md:245
Goal 原文：计划 §2.1；sha256=731d1ca284792c8aefcc97bfb69bc5734698c337bd0475f48d3177c5584815ea
权限门：未绑定前禁止产品施工、真实模型调用、部署和V1日落
### V2.R1.1 · 下一动作：核对/绑定Goal

输入：INDEX→context→current state→本计划§2、旧baseline state、准备审计；不读聊天作为必需输入。
动作：用可用Goal接口读取旧Goal和当前线程状态；无接口明确报告；若旧Goal仍active且新目标不同，提出暂停旧目标/新Goal线程选择，由授权方操作；用户确认后逐字创建§2.1objective并取得真实ID/读数。随后goal_binding required、Phase1 active、R1.1 done，next选择R1.2。
输出：`refactor/goal-binding-<timestamp>.md`，只存ID/状态/正文指纹与授权，不含secret；state精确更新。
验收：没有两份active本地记录，不用旧ID承担新objective，不假暂停旧Goal，不凭计划签署推断已创建。
失败：保持prepared、pending R1.1与精确blocker；无产品施工/付费调用/部署。
```

额外smoke初次把“重复任务必须由新入口报错”作为层级期望；实际已有J6优先拒绝，改为接受正确拒绝，不修改守卫。

## 用户要求证据映射

| 要求 | 权威/当前观察 | 判定 |
|---|---|---|
| 详细实施计划落盘 | 当前plan的单表、明确Phase字段、26张唯一卡、8门、UI协议和完成矩阵；实际冷读验证数量/唯一卡/无依赖环 | proven |
| 控制面校准 | INDEX唯一路由、历史基线、新prepared state；守卫+对应正反例 | proven |
| 拟创建Goal原文 | plan§2.1；实际--goal-text与JSON相等及正文hash | proven（仅拟建，未创建） |
| 下一任务不依赖会话 | 新uv独立进程从INDEX读state→plan→R1.1卡/权限/阻塞/原文；14文件只读全等 | proven（系统Goal实际操作仍需可用接口及授权） |

## 修改前后指纹

下列不包含本审计自身，避免递归hash；新文件before为NEW。原始字节快照保留在前述工作区路径，正式仓库历史baseline承担日后恢复路由而不是依赖临时快照。

| 相对路径 | before sha256 | after sha256 |
|---|---|---|
| `docs/INDEX.md` | `8819643503c94f92c19d3bdcc7e7125af0bc40a6dc639d407e4b2317f5071313` | `89c160be2b540a8a06ccac3ddcee9a067043103b9c389797ad0e7e9daf0aa3a6` |
| `AGENTS.md` | `0fc9a47b138b44b5ddd549928cbcb4276eb37d754f6ce8b2a63c5b298af9ca94` | `5931f0789ad7e6f9037e85ae2f5ad16c94768dae74069b11703bd6fbf1fefee7` |
| `README.md` | `5a7f2cfff0a468a44f1ab8344d3e1f3a81d85b4f53a5bc05a4da82e941a85e88` | `767581637d1f46c81d2ffc5c77195890df1e18d719de05e6dc3b07c2951341a1` |
| `docs/product-v2-project-context.md` | `bef9a983df471493937fade86d439053855929516eca0614f3f3da21f94ab30d` | `8a2c8f1e519fccf69d0348cdaf0a9e38922864288f32c36b02363c812fcc1b85` |
| `docs/product-v2-goal-and-implementation-plan.md` | `0d7d06c61ce0aafca2fa1f3c02e415eb7cbb0c2adcced91dd0d57f84ed9056ca` | `d62b5fe1718eb17b6334b9c54f062606ec2541d0adbaa544feb7ad1d96b2e374` |
| `docs/product-v2-ui-contract.md` | `3f0d151a36d960f2517ab0fc29f92593057edc20a5ed5914ee87cdfd7af5e137` | `e9aa6a75bdfc72b8f036591f44f60b3d69cf5c819eb7684ab5101efb4ddef62f` |
| `_working/amz-listing-kit-product-v2/state.md` | `3325a8bb605c4af9fee5900831c1d667be617242a7c8a1fe8cadbd5f9df02d32` | `edfcc7226ec15daa392e2f77001636130ab2faa267e2092c32d3edc0bbb624ec` |
| `tools/check_project_state.py` | `af8c332743c44d110f8bac53d17d4c1f0ae8323daf52bba55345035ed8321206` | `af8c332743c44d110f8bac53d17d4c1f0ae8323daf52bba55345035ed8321206` |
| `evals/probes/project_state.py` | `120eec7c17b2f7b77ade73d5d85b6a5e3e821f38bba3e72a0646de8b0c14591a` | `f3a76fd8da6fdb342c5eb505bca6c1c9d654f49e4a9a43f25c7e19a09e726db8` |
| `_working/amz-listing-kit-product-v2/tasks/v273-walkthrough-kit.md` | `58b10d2f7753ee8b44e6c3f3b0c775ed70de28c14ae4b6dbccc9efa99933476e` | `8c12bae2a3ded874965c7a5a9223f2795ff79431816c08d73140382e567993b5` |
| `docs/product-v2-refactor-plan.md` | `NEW` | `0cee3290196ac8869a14d1c215a1e646eba9f49c52d56b5e6e3023d9d925f591` |
| `_working/amz-listing-kit-product-v2-baseline/state.md` | `NEW` | `47b3a6343725f16dd6513e6a2553dc88d2e3382651c90a52f2821c78d6077d37` |
| `tools/refactor_resume.py` | `NEW` | `4bb4d574828ccbdab876d6f871c463e98e8f9a0fd247c2b43ac0b5c1d3b22195` |
| `evals/probes/docs_index.py` | `NEW` | `bf567bde7e8bf27b03f24ce968b14681f8235406b173df86f030a261c8f7b0fd` |
