# 2026-10-04 项目规约完善记录

> NOT-AUTHORITY：本轮时间点证据，不是另一份计划、进度或产品验收。业务合同唯一在 `docs/product-v2-refactor-plan.md` §14，进度只在 current state。

## 1. 授权与用户决定

用户要求：“以之前的讨论为启发，现在开始完善项目规约，有什么问题或需要澄清的及时向我提出”。本轮仅编辑既有规约及必要恢复记录；无产品代码/配置/CI/依赖修改，无供应商请求、付费、Git提交/推送或部署，无Goal创建/生命周期写入。

沿用已确认的“现有模型选择＋自己的key”和“按需发起复核”。发现现有整套报告/Unknown门与可选复核含义存在歧义，向用户明确询问“未做AI图片复核时，是否允许导出交付包？”用户选择：**允许，AI复核是可选辅助**。确定性报告/硬检查、人工采用、字节/hash和原动作来源完整性继续强制；未做AI必须如实标记，不能伪造PASS，也不能将not_run伪装成模型Unknown。

本轮 `goal.get` 实际返回 `No active goal`。历史原生ID、绑定证据、阶段/任务完成记录保留原证明范围，不作为本会话施工/发布许可；§2.1原文未改。恢复仍指向blocked `V2.R6.3`，UI身份仍draft，不声称G6/工程/真人门通过。

## 2. 规约落点与源码核对

- 计划§14集中：人机分工、业务对象/source/actor/status、人工/辅助共享路径、八个既有用途及custom的信息需求、动作前置/后置/恢复、本地编译与精确失效、真实图文理解边界、有限模型/Agent边界、可选AI交付政策和完整代表任务；对齐既有R4.3/R5.3/R6.1–3及RC07/10/14–16，不新增任务ID或另一份PRD。
- context§5.1说明现有Module/Interface/Seam及消费位置，目标与实现分开；修正仅qwen生图、VLM型号待定、第二模型/预算未批准、同步必须task及仅语法门等旧描述。未变更技术选型或引入框架。
- UI§1–8投影：人工入口、按用途缺项、六个导航不是业务门、默认/就地高级/非秘密诊断共享状态、实际发送摘要及一次外发确认、稳定候选/返工/采用、明确可选AI及有限模型/key设置；历史原型保留。
- INDEX只更新既有文件管辖说明；state只更新证据/明确阻塞/未知及本轮范围，不改阶段/任务状态、依赖或历史Goal字段。

关键源码证据（只读，非本轮运行验证）：

| 已核对事实 | 源码位置 | 规约含义 |
|---|---|---|
| FactSlot来源/状态/actor和标量类型已有注册，三项critical为名称/品类/保留特征 | `domain/slots.js:34–78` | 复用同一业务合同，不建立另一套人工事实对象；其他注册字段不自动全局必填 |
| 八个模板已有集中依赖，尺寸接受size_summary或绑定事实，成分实际template为ingredient_composition | `domain/suite-plan.js:88–145` | 信息需求加强由唯一domain承接，尺寸非空不等于有可标注数值/单位，不在UI/网关复制表 |
| 文字分析只发送参考图元数据，明确没有像素，reference_images_sent=false | `providers.json:12–29`、`v2_dashscope_semantic.py:102–119,257–271` | 不能把现有semantic链当视觉理解；复用qwen-vl传输但需商品事实提议合同 |
| 复核请求要求candidate、参考图≤3，图文传输已有data URL形态 | `v2_review.py:140–175`、`v2_dashscope_review.py:57–106` | 传输可复用，审核schema不可代替商品分析；目标图文上限是新增合同，不声称已实现 |
| 图像服务读BYOK头；理解/单图/整套复核和客户端未形成全用途凭据消费 | `product_v2_server.py:404–432`、`workspace.js:1276–1279`、`generation.js:411–416` | 设置框/图像header不是三用途闭环证明，归既有施工责任 |
| 单图确定性报告本地构建，AI有独立主动复核动作 | `generation.js:324–376,385–416` | 保留本地测量及当前报告门，不把所有ReviewReport等同付费AI报告 |
| 整套not_run被投影为outcome=unknown与UNKNOWN finding，导出收集Unknown/知悉门 | `suite-review.js:427–457,533–544`、`export-gate.js:189–225` | 迁移未运行AI与模型Unknown的耦合，不删除确定性报告/完整性或生成提交Unknown保护 |
| 状态守卫已允许有匹配blocker且依赖完成的blocked恢复点 | `check_project_state.py:479–496` | 修正计划§2.2/R1.1/§12开头的旧恢复描述，未修改守卫或新增控制框架 |

## 3. 代表任务的规约层核对

纸面核对计划§14.9与UI落点：人工不分析仍可填事实/建任务；尺寸缺失只阻止尺寸消费者；同商品图文提议经人确认后共用编译/执行；默认一次发送而高级人工文本受保护；partial期间直接比较并局部返工不改无关图；刷新/换设置按原身份恢复且Unknown不重提；无AI导出如实not_run；两类ZIP以采用原动作与实际字节为准。

这是**规约层的路径/权限/后置审阅**，没有运行产品、请求模型或读取真实生成图片；不是八条浏览器场景通过。真假图质量、真正图文理解、全用途BYOK、走查及新交付政策落地仍未验证/未实现，不以旧done/旧付费/旧发布证据替代。

## 4. 原字节快照与指纹

改动前原字节保存于 `_stage-amz-control/spec-consolidation-20261004/`；五份快照的完整文件SHA256与改前源文件逐项一致。以下值来自原生 `sha256sum`，不是reader输出拼接。

| 文件 | 改前SHA256 | 改后SHA256 |
|---|---|---|
| plan | `f62a7e8618c2f79170424a6a958d5040cb3e326f6dff356dc1950390d4c07c82` | `e3f60af0c88335914b3b73aa86578b587a047a2fca9d5cd1bcbf6a67a198ff19` |
| context | `8b3392eaaed0e577a6379594762406fd4df2cbfb17dac4680afca667211a9569` | `e793f0c8730b25d4db32edb0355e00636430a392c189462e04457668c133f77a` |
| UI | `4536027041793e6c86dc1b7ea3777a5f53ce69105738b5ee169efd29f8dcc1b4` | `3b47ec3c5c7355c158c2e4ad7713370d3ef09759fe98f655b0533bb2232f7411` |
| INDEX | `0c0f07668718c42d662cd221fd3f09f0d123cc8fb42cbdd8219b1ad371572d88` | `d0bd8e4de532a7da97f6f7598e60b0a7818703820da54cfdc7c64c93ab3e335e` |
| state | `9c17fd46273183d7b5708de7efc87b52e62f1c6cd866ab00a7cffeacae419707` | `1c4ae33d983be9a21bc61d2c1d61f85b4c3c3bb25bbd904e26e15cb9fd157c9f` |

## 5. 针对性验证

实际串行执行，整条命令退出码0，耗时15.71秒：

| 检查 | 实际结果 | 证明范围/限制 |
|---|---|---|
| `uv run --locked python tools/check_docs.py --no-run` | 全过；登记61/实际61，直接依赖/锁/vendor/模板映射一致 | 文档登记/静态一致性；明确未执行文档中的legacy命令，不声称这些命令本轮可运行 |
| `uv run --locked python tools/check_project_state.py` | J0–J10全过；工作记录5份 | state与计划任务/依赖/历史绑定证据结构一致；不是当前系统Goal查询或产品验收 |
| `uv run --locked python tools/refactor_resume.py` | PASS；8阶段/26任务；唯一next=`V2.R6.3`，明确blocked且只准解除三项输入/权限门 | 实际冷恢复入口读取本轮任务卡，未回到旧发布或R1.1，不执行受限产品动作 |
| 冷恢复输出Goal原文SHA256 | `3f9f1842d67d063fa9d8cfbbaf60eb5971fe24b46502c97455241ccac40d4607` | 与原指纹一致；未改变§2.1原文。输出仓库历史active/required观察，同时明确脚本不查询系统Goal；本轮实时No active goal不能被该历史读数覆盖 |

无产品代码/配置改变，不新增测试、验证器或运行产品回归，不重复既有64向状态探针；阶段/任务状态及依赖未变。规约层交付成立，产品落地/可点击原型/真实图文请求/图片质量与人审均未验证，不据此称工程完成、可发布或Goal完成。
