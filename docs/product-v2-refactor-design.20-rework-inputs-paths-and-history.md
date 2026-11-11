<!-- 拆分件 20/29 · 父文档 docs/product-v2-refactor-design.md -->
# §13当前设计：双模式返工、五条路径与格式历史
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.19-decisions-copy-and-module-owners.md) · [下一主题](product-v2-refactor-design.21-prompt-attribution-and-quality.md)

### 13.6 双模式返工与真正模型输入

| 模式 | 实际图像及顺序 | Prompt语义与结果承诺 |
|---|---|---|
| edit_candidate（默认） | 第1项为固定问题候选的原Blob；后续为本图消费的商品原参考依据 | 指明每图用途、具体问题位置/现象、允许修改和满意部分；原商品事实优先，候选幻觉可修。输出一张新整图，**不承诺未改像素完全不变** |
| regenerate_original（另选） | 仅本图商品原参考依据，不发送历史候选图 | 重新表达完整目标；问题候选只是诊断记录，界面标“模型来源：商品原照”，不能冒充局部编辑 |

在现有 `PromptReferenceSelection`／冻结request.references中增加非秘密语义元数据：`uses: ("edit_source" | "product_truth" | "style_reference")[]`（非空、不重复），`sources: {kind: "candidate" | "product_input", document_id: string, version: number, asset_sha256: string}[]`（version正整数，hash为64位小写SHA256，所属project由意图固定）；数组顺序即模型图序。其他既有sha256/media_type/角色字段继续消费。候选的传输role使用当前有限词表中的`other`，**role不是编辑含义**；语义由uses/来源与实际Prompt共同表达，不增加商品上传角色或谎称原ReferenceRole已包含编辑模式。

模型输入构造规则：

1. 从原项目确切记录读取候选Blob和商品依据；验证来源与媒体类型/字节/hash。先放编辑源，再依照现有本图绑定顺序放商品依据。相同字节合并为一次实际输入，uses/sources保留双用途，文字图号按合并后的顺序编译；不复制新的候选资产。
2. 最多实际3图、单张≤当前profile的10MiB，PNG/JPEG及尺寸/字符限制取当前有效profile。编辑源占一位；商品依据超容量时阻断并让用户选择本图必要依据，不悄悄裁图/丢商品约束/换模型。无候选/能力不允许参考输入则禁编辑并说明原因；原照重生成须人明确选，不能自动降级。
3. `.uses/.sources/mode`只进入项目内冻结/摘要/归因链，不直接当供应商字段。网关POST继续白名单：action_id、prompt、references（role/media_type/sha256/data_base64）、size、n=1、prompt_extend=false、watermark=false、output_format=png、model_id、target与credential_source；不偷偷加seed。
4. 两模式均用既有两个Image Adapter：Qwen把按序data URL图放在user.content前段，单text在末尾；parameters实际仅size/n/prompt_extend/watermark（未设置seed则不发）。Ark用按序image数组＋prompt、size从`*`映射`x`、response_format=b64_json、output_format=png、watermark=false。二者body不要求字节同形，也不凭网关字段声称Qwen额外发送了output_format。
5. 模式、问题候选、实际图序/用途/hash、Prompt来源/文本、配置或真实输入basis变化使旧预览失效。仅新候选晚到不偷换已固定源；其原件仍在且所消费依据不变时，旧源可以继续作为此次返工依据。

人工全文：默认不覆盖。当前为人工稿时，准备返回需要明确选择的投影：“保留人工全文并核对本次模式/图序”或“使用系统返工稿，保留原人工历史”。未选不外发；人工模式的实际新全文由用户在高级入口看过并明确确认，系统不暗加/改正文。普通系统路线不用进入高级编辑。确认后追加新Prompt版本，原人工版本/草稿不删；所见之后basis变更返回stale。若Prompt已追加、后续预约失败，返回实际已存ref并零新POST，不能伪称零写或删除历史。

### 13.7 五条路径：正常、失败、并发与恢复

| 路径 | 前置与正常后置 | 失败/并发/恢复 | 正式消费者上的验收动作 |
|---|---|---|---|
| 输入与确认 | 原照/资料保存；只确认当前来源、相关事实及必要展示决定；方案能解释每图依据 | 不可读图不入库；容量/保存/OCC失败保留稿；旧分析不套新输入，Unknown不默认重分析。重开读已保存事实，未保存稿不冒称已存 | 上传真实本地字节→填资料→人工/显式AI提议→确认→改已确认值；看实际记录/Prompt前进且真人工稿保护、无额外POST；无尺寸只阻对应图 |
| 生成及部分失败 | 方案/Prompt/profile当前；用户看actual scope一次确认；每图一个action，新候选不自动采用 | 一图失败不删其它成功；Unknown只观察原任务；双击/跨tab不重复消费；停新增仍保全已发结果。关闭后未确证提交结果为Unknown，不能保证后台继续 | 勾选明确范围→看摘要/图序/次数→确认；替身制造成功+明确失败+Unknown，成功即看/采用；核准确POST、action、Blob与无自动重提；排除理由对应每图 |
| 双模式指定返工 | 从实际查看候选启动，默认编辑；源/草稿/模式冻结；确认只影响该shot | 缺源/字节/超限/手工稿未选/旧意图/在途均阻断；换模式须重看；晚到不改源/旧采用。失败保留旧候选和采用，恢复原记录 | 同一shot先编辑、再明确原照重生成；独立核Adapter解码图hash与顺序，编辑含候选/原照，重生成不含候选；核无关shot文档/Blob逐条不变；取消/过期/双击零额外POST |
| 采用与交付 | 确定性report已就绪、无硬阻断；人工采用看到的候选；交付只消费采用与原动作冻结Prompt | 报告保存失败保全图片/旧采用并禁越硬门；新候选/新Prompt不自动换选。构包期间输入/采用/report变动按现有围栏失败，不下载假成功 | 查看v1、采用v2时点v1动作确实操作v1；只采用已看到的合法对象→明确检查→真实交付ZIP；解包核图片原字节、manifest原冻结Prompt，AI未跑如实标记 |
| 刷新与恢复 | 原生项目ZIP是完整一致只读快照，含原图/候选/文档历史和非秘密来源 | 坏包/未知schema/hash错/容量失败不半导入覆盖；DB或报告恢复错误可见。BYOK只内存，重开为空；在途/Unknown不自动另发；唯一恢复包不清 | 实际下载完整包→独立空profile同版本导入→刷新/重开；逐文档身份/version/payload和Blob字节精确匹配；再指定返工/采用/两包导出，新增历史单独计，不能要求整个ZIP追加后仍同hash |

后置的读取只能取真实消费者产物；直接播种候选只可用于精确故障反例，不代替普通用户全链。正式fake链仍必须真的点击/上传/保存/下载/导入，不拿内存原型签业务验收。原 `walk_to_adoption/walk_to_deliver`、6_2/6_3/5_3/5_4及对应domain消费者是资产，按前提复用，不另建第二套walk。

返工提交关闭面板时，把焦点归属记录在禁用提交控件之前；原项目/图/候选仍当前、且用户未将焦点移到别处时，收起后回到可见返工入口，不把焦点留在body，也不因晚到结果抢走其它控件的焦点。取消与新结果保持原查看对象/精确草稿的既有合同不变。

### 13.8 格式与历史：一次切换，不篡改原动作

明确的下一版payload升级：StyleSpec/ShotSpec由1→2（结构展示决定/上图文案）；ReworkDirective由1→2，contract v2.5.4→v2.5.5（mode、明确问题候选）；Prompt由1→2（真实refs用途/来源/双模式）；Confirmation由已有1/2→3（该新请求完整冻结快照：实存历史2已带role/sha身份，不能重定义2或补造用途/来源）；Attempt由2→3（消费新冻结request）。具体实现同包修改各domain/type-contracts/校验器/owner/视图/Node与浏览器消费者。值与hash是新版本真实计算，不提前写假记录。

不新增对象仓/索引，故storage schema仍2、记录信封仍1、项目包信封不因payload扩展乱升。现有网关字段与有限协议/能力块不变，不为元数据另发供应商参数或无谓前移执行target；旧task观察仍按原模型/protocol/目标核对。若实施发现实际能力块必须变，先处理原在途task消费者，不直接把它们变成无法核对的Unknown。

历史原JSON/Blob/冻结hash原样保全。现有版本解析器按明确schema分支验证旧/新数据；旧Style/Shot只在读投影缺少新决定时显示未确定，新动作经明确保存写新schema，不能原地重写老Prompt/attempt。旧返工未声明模式就显示“旧记录未声明模式，以原冻结图序为准”，不得自动推成编辑或补造出站事实。新记录严格新合同，不允许未知版本以可选字段蒙混过去。

这是当前项目内的记录保全与一次性读写切换，不是维护所有旧版本/schema/项目包的迁移服务。当前已交付包自身含有的旧动作、旧采用和冻结输入仍须准确显示；旧无mode不补造事实，新命令只走新合同，所有新消费者同包切换。项目导入完整验证受支持的对应版本与原字节后原子入仓；未支持版本显式拒绝，不静默删字段、清用户库或让旧客户端吞新schema。后续不再扩展历史兼容范围，旧运行面按计划清退。

