<!-- 拆分件 08/29 · 父文档 docs/product-v2-refactor-design.md -->
# 实施规格：生命周期、报告与两类ZIP
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.07-reservation-and-observations.md) · [下一主题](product-v2-refactor-design.09-build-and-release-spec.md)

### 10.5 生命周期：把关闭分成禁新动作、保存草稿、脱离视图

会话负责navigation generation；项目runtime负责自己owner/订阅/URL/timer。runtime目标局部状态 `open | closing | detached`，不落库、不另建业务状态机。一次切换只有一个在途transition；开始前同步占位并禁用导航/新业务命令。重复open/close返回稳定busy，不排万能异步命令队列。

1. A→B前先将A标closing，停止新增预约/轮询调度与新命令，捕获未保存草稿及其seen版本。已发HTTP不假称取消；旧实例仍可按冻结project/action保全响应。
2. 按原项目/OCC保存草稿；保存失败或冲突须传播到session，不像现有workspace.close捕获后继续清项目。取消本次切换，A仍可见并恢复接收动作，显示保存失败，B/pointer/generation不提交。
3. 保存成功后退订view/settings通知，清timer和撤销本实例URL；A变detached，推进会话generation。资源释放不清用户业务记录，不把保全callback依赖的原身份归零。
4. 打开B创建独立runtime，按inputs→prompts→generation→adoption→delivery读取并校验记录，完成后再接view及宣布open。恢复失败保留已保存项目/历史，传播失败，显示“项目已保存、工作区打开失败”，不能吞错显示ready。pointer只作最近项目轻量提示，不作业务权威或跨事务成功凭证。
5. 整个transition在finally释放导航占位；重名/改名不推进generation。boot失败释放自己新建的资源；不得通过清库/强刷新/重跑把失败变成无痕成功。
6. `ActionSnapshot.alive()`只证明当前显示身份；新业务还须runtime允许新命令。保全不受alive一票否决；采用、导出新提交在会话关闭后禁止，已构成的artifact不自动在B下载。

反例：closing期间连续点击A/B；草稿OCC冲突；旧分析/生图返回；B恢复report抛错；A改名；关闭后旧finally。新项目不被旧结果渲染/改选，旧原结果仍可恢复。复用原session生命周期合同，不引入AbortController“取消上游”幻觉。

### 10.6 报告、人工采用和两类ZIP：快照一致不等于实时当前

**报告所有权与AI状态**

- adoption创建/恢复确定性单图report；delivery创建/恢复确定性整套report。project open可补必要的本地确定性报告，但失败可见且门禁不通过；生成/打开比较/采用/导出都不自动发AI。
- AI只由明确单图/整套动作发起。未运行、运行失败Unknown、真实成功分开；沿用现有not_run及模型unknown合同，未运行不制造UNKNOWN finding，真实失败不伪装not_run。
- 报告头取决于当前引用/指纹，不取“最后完成callback”。AI请求捕获原source、候选/报告seen版本；目标 `commitReviewReport` 在现有repository中用同一documents写事务核对消费投影和seenReportVersion，才append并更新当前投影。旧输入结果或报告版本冲突返回stale/未登记，保留原报告与请求身份/失败事实，不自动重调用，不悄悄覆盖新报告。确定性重算保留仍匹配的既有AI块及真实失败，不能用本地重算抹掉Unknown/已知悉要求。
- ack钉住既有规则、对象和报告身份；新报告/新候选不继承一个泛化“我已确认”。不生成空报告/PASS绕门。原task恢复配置仍从原身份取，单图AI准备不反向依赖delivery。
- `reviewIsCurrent`现有单图合同只证明candidate/sha/审核合同匹配，不冒充当前事实/规格/整套门禁。后者仍由消费投影、当前suite report及交付围栏验证；不为扩展报告身份偷偷改schema/造来源字段。`commitReviewReport`沿用§10.3数值0/OCC/事务寿命规则，由adoption及delivery各自提供原领域输入，禁止UI自行写报告。

**目标 `commitSelection`**

事务外读取并hash候选字节、校验原attempt/候选/单图当前report，构造既有人工SelectionRecord。输入含完整decision（含取消采用）、seenSelectionVersion（首次0）、candidate/attempt/report精确ref及消费投影。事务内读取selection当前头与所见版本一致；保留原合法旧candidate，不强制候选shot头等于所选版本；精确candidate/attempt、report当前性及asset键再校验后append。取消采用只核对原selection头，不要求不存在的candidate/report。冲突不重定向到最新candidate，原采用保持。

**目标 `readProjectSnapshot`**

同一个readonly `withTransaction(["projects","documents","assets"])`读取项目、全量文档历史及资产记录；documents用现有 `by_project_kind` 项目前缀范围，assets用 `by_project_id`。返回Blob句柄和数值版本向量，字节/hash/压缩在事务完成后进行。完整项目ZIP就是该线性化时刻的历史快照；后续合法写入不使它“混合”，不追加“整个压缩期间禁止任何写”的二次围栏。

**目标 `commitDeliveryRecord`**

交付ZIP仅用同一快照的已人工采用候选、原attempt的Prompt版本/hash、当前单图/整套确定性报告、ack及资产字节。先构包/hash，提交前一次readwrite事务校验：selection头、所消费事实/用途/风格/规格投影、单图report/suite report/ack身份、精确candidate/attempt/原Prompt链及资产键。不能只围栏“selection+suite”而漏掉规格/report。无需钉住无关新candidate或当前编辑Prompt头。

任一相关头变动须在事务内按领域指纹/投影判断是否改变门禁所依赖结果；影响则冲突，不落export_record、不提供下载，保留原采用和诊断。完全相同exportRecordId/payload可返回原记录；相同ID不同payload拒绝。成功后再下载；后续修改不会倒写旧export记录。采用/交付事务持有asset store且再查键，完成后的Blob句柄供该快照使用；不能把一次存在性读称为跨事务永久租约。

当前 `assets.delete` 入口先查实际引用/消费者；引用资产不允许盲删。仅删除已解除引用素材或项目级cascade；无实际用户入口则不要为“垃圾回收”新增功能。import碰撞分配新projectId，不能覆盖旧库；不扩展跨版本降级读写或更改schema。

