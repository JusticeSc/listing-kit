<!-- 拆分件 14/29 · 父文档 docs/product-v2-refactor-design.md -->
# 历史基线：凭据整链与旧运行面清退
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.13-historical-baseline-startup-and-compare.md) · [下一主题](product-v2-refactor-design.15-historical-exit-and-current-entry.md)

#### 11.6.4 B：精确凭据、辅助整链与原结构准出

凭据：已有等长哨兵和`<length:n>`只证明通道/长度，不证明接收值；FakeVisionSemantic的`apply_credentials`本身是no-op。复用registry当前匹配注入实例并调用`apply_credentials(api_key=byok)`的正式路径，在测试实例/既有transport或llm_factory中仅保留内存精确相等的布尔值与计数。文字/图文理解、生图、单图/整套复核按实际消费者分别证明接收预期用途key；等长交换哨兵必须使断言失败。不得把浏览器发送header、mock返回常量或长度当实际Adapter接收证据，不改生产验证器的key值语义。

在明确输入哨兵后扫描DOM非凭据回显、localStorage/sessionStorage、全部相关IDB文档及Blob字节、响应/错误/控制台/服务日志，并用ZipFile解压完整项目与交付ZIP的所有成员再扫；只记结果，不落盘哨兵值/真实key/hash。合法密码输入框、单次request header与测试provider内存接收不算泄漏表面。复用现有无key、default-trial closed、reference缺字节、旧ZIP导入和两Adapter离线transport用例；各反例必须先满足其它前置，不能用“缺字节”证明无key或用constant证明导入。

旧任务补key/恢复还须经现有status/result路径：原action/provider/model/credential_reference保持不变，错目标明确拒绝且零出站，补原目标key只核对/取回、不产生新submit。优先扩现有`4_1`及packet08消费者；生产registry/credentials/server/Adapter仅在上述实际反例失败时做相应修复，不顺手加校验/重试/抽象。

辅助整链：独立临时profile与真实页面操作，从建项目、填写事实/导入许可商品参考图、明确图文理解、可编辑事实/用途、默认Prompt准备、一次整套明确外发，走到比较/指定候选返工/人工采用/可选复核/交付ZIP/完整项目ZIP，再清空key、reload/新profile导入恢复。不得用`SEED_SLOTS`或内部文档灌入代替商品资料/理解到槽位的消费者；既有`walk_*`用前先核对其seed行为，只复用真实UI动作部分。分别保存关键截图并实际读图解释控件/对象/状态，不用截图文件存在代替观察。

记录独立后置：事实与槽位来自此次输入、外发张数/范围一致、旧采用未被新候选覆盖、返工source精确、项目ZIP文档payload与资产字节/hash相同、交付ZIP选用候选/来源/manifest如实、重开后BYOK为空且历史/采用可恢复。不自动触发AI复核、不因未复核挡导出；确定性报告/人工采用/硬检查仍强制。本地fake用于可控异常/Unknown/过期与安全证明，不能提升为真实图文质量证据；C17/C15仍等待真人。

2026-10-08当时读数为image8、semantic/VLM5，当时补充门最多5张生图/2次理解复核、增量≤3元/累计≤5元，原拟“一轮理解+四张整套+一次返工”只属该时点方案；**不是当前额度或调用授权**。当前只补合同确实受影响/缺失部分，依真实ledger与state核次数/费用、安全注入和素材门，不能重新消费旧额度或重复购买已证链。调用前仍须核官方协议/价格上界、许可/hash及获准通道；Unknown保留次数/预留、不自动重提，准入不足只停对应动作，不用fake补签真链。

结构六项逐项引用当前生产消费者及实际运行证据；源码已删除的reviewAccess/setter与旧Map迁移不重新实施。返工编排残余按A2处理；其它不满足原准出的项须同闭包实际修复，不能用类型绿/空扫描/“后续再重构”签署。此处只核对原结构门，不新增总体架构、全仓TS或新schema。

#### 11.6.5 C：复用WIP并一次清退旧运行面

依赖与R7.3准入成立后，以`15faa65`的114删/3改/9恢复材料为差量来源，不直接合并未收尾分支。先核对当前main和WIP的语义差量及冲突，保护之后的消费者修复；同一个清退包包括必要消费者迁移、原件/恢复材料证明及旧实现删除，不能让两套活逻辑并存到下一包。不是先清退再绕过G6补验。

1. 逐用途处置`app/server.py`的V1 flags/dispatch与旧doctor，`verify_v2_1_2_project_home.py`的V1 route案例，以及pre-V1 `run.py/web/renderers/config slots/catalog/docs cards/tools`真实调用；必要文档/状态/P治理功能迁现有控制入口，产品旧执行链删除。共享`src/product_facts.py`/`src/review_contract.py`保留有实际用途的部分：当前消费者在`eval_dataset.py`/`pilot_registry.py`，不是假定V2 server/provider依赖，也不能因产品旧面删除而误删P治理。
2. `tools/check_project_state.py::_evidence_ok`及done阶段J5、done任务J6两条调用统一按同规则处理：只有superseded所有者、精确获批退休路径、原commit/bytes hash及可达归档全部满足，才把“当前路径已退休”记历史说明；当前证据、非退休缺失、无有效归档仍error。覆盖原阶段/任务、退休/非退休及归档篡改反例，复用现有`evals/probes/project_state.py`，不只修改task调用。
3. WIP全量tracked-manifest的3282条仅识别历史原字节，不是全部可删除/退休的许可。单列实际114删除及此次明确核对的pre-V1新增退休子集，与原commit/hash/可达原件对应；守卫只接受该精确子集，不能把“全manifest成员+当前缺失”解释为合法退休。main路径不可达的WIP材料须从已核验Git blob恢复到稳定位置，不能以临时路径或单个hash声称可恢复。
4. `check_docs.py`依赖`src/schema.py`/cards/`run.py --dry-run`等旧消费者时先迁其必要检查，再删旧producer；不要把“删除检查”作为迁移。核对依赖引用后才移除仅旧面使用的包；若`jsonschema`确认只剩退休消费者，则用现有uv依赖工作流同步pyproject/lock/context，不手改lock。README/AGENTS/context/INDEX/design中已被新工程清退授权取代的“真人前一律保留V1”说明同包更正，保留C17/C15限制、旧历史及用户原件。Docker排除规则只删真正死项，runtime闭合白名单不放松。
5. 复用稳定`asset-continuation-20261008T054352Z/data/manual-project.zip`（原SHA256 `4007b9b1a3b2f14c1fa4e851bdc1ab52ebc690fc02d4556f65b81a1ff4e3ff39`）及既有`6_3/6_2`项目/交付消费者，先验证当前字节和同版本对应再用。独立profile导入、重开，逐文档payload/资产字节核对原数据；删后做真实指定返工、人工采用、两包导出/恢复，新增业务记录单独说明，不要求追加后项目ZIP整体字节还相同。旧R7.3私有probe只有counts/hash，不能代替采用当前性、payload和返工证明。

最小门：受影响文档/状态/既有64向状态探针、必要类型/生成产物检查、删后真实路径与恢复。控制改变如影响验证登记再跑其已有守卫，非每包机械重跑全部平台。失败保留原件与候选，不删除唯一数据恢复包；无法迁移独有必要用途须升级，不用改名legacy来伪装清退完成。

