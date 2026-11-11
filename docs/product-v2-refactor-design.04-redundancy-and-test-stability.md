<!-- 拆分件 04/29 · 父文档 docs/product-v2-refactor-design.md -->
# 重复治理、测试稳定化与类型一致
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.03-transactions-and-main-paths.md) · [下一主题](product-v2-refactor-design.05-history-and-delivery-exit.md)

## 6. 重复与冗余：分类后合并/删除，不只拆文件

| 现有问题/位置 | 具体治理 | 不能用什么冒充完成 |
|---|---|---|
| workspace旧suiteReports/selections/确认等直读、旧reset与链式执行 | 逐状态建立唯一owner；所有读改投影，所有写改业务命令；owner恢复/销毁替代工作台reset；同切片删旧声明/回调/旧helper | 分文件仍共享可变context；只修未定义变量 |
| authorization独立状态 + generation确认保存/消费 | 合并到generation，删除 `authorization.ts/.js` 及相关类型/构建/测试旧引用 | 新文件pass-through/re-export/旧路径兼容alias |
| generation单图reviewRequestBuilder/review报告与下游复核交织 | 单图报告归adoption；generation只提供候选与原动作投影；移除review请求callback回边 | 两份review Map同步更新 |
| SelectionRecord被当candidateId使用 | adoption明确提供 `candidateIds` 与 `records` 的不同只读类型；suite/manifest消费正确值 | 在每个调用方加 `any`/猜对象字段 |
| shared helper与整份verify脚本互相import | `tools/v2_verify_shared.py`仅公共宿主夹具/稳定UI前置；领域用原生Node，浏览器用公共helpers，工具不借另一完整验收脚本的全局状态 | 同一seed正文复制多处；万能测试工具包 |
| 小而真重复的SEED_SLOTS/资料输入/upload等待 | 共享确实相同的业务前置与fixture；验证不同后置，不复制相同成功行 | 因字段名相似合并不同语义；扩大固定夹具掩盖用途缺项 |
| evals/product-v2/node/_gen.mjs以HEAD裁源码/词替换 | 在现有生成入口移除旧源码裁剪/HEAD依赖；行为夹具直接import稳定domain Interface；若不再有实际生成用途则删除生成工具并迁所有调用 | 从历史源码拼“测试专用运行时”；保留字符串补丁来稳定测试 |
| 手写JS与TS、生成名单与类型名单不一致 | 一个TS为唯一手写Implementation，浏览器JS由该源生成并纳入新鲜度；源集/实际emit结果对齐，生成校验覆盖被依赖带入的迁移TS | compiler program读到即算构建覆盖；mtime/语法绿灯 |
| 参数/协议/能力/错误分支跨Python和页面重复 | 仅真实相同的传输/有效配置规则集中，业务schema继续独立；复用现有registry/credentials/outbound/domain判据 | 通用schema生成器、把商品理解和候选复核当同一请求 |
| 过大函数/大量薄wrapper | 按变化原因、决策及数据所有权拆/合并；调用方只传意图；无决策/无状态/无独立消费者的转发删除 | 固定行数分割、限制函数数量、新Module数或测试数 |

每个施工包在本来要改的依赖闭包内主动检查上述模式，并在该包完成说明记录“删/合/保留及理由”。不等用户点名；不借结构治理扩张到无关业务、未授权V1删除或新框架。

## 7. 测试稳定化与类型/交付一致

### 7.1 断言分类与迁移

| 分类 | 处置/既有落点 | 真实判据 |
|---|---|---|
| 文案/函数名/源码位置/数组数量/纯转发回声 | 删除，不重钉；如selection-contract的措辞/枚举形状行、intake验证器读workflow文字猜tar/容器合同 | 保留它原本想证明的用户行为；没有行为内容就不补新永久测试 |
| 纯规则/边界/状态转换 | 复用 `evals/product-v2/node/` 原生domain入口 | confirmed权限、实际依赖stale范围、人工Prompt不覆写、not_run与Unknown分开 |
| 存储/OCC/恢复/ZIP | 复用现有Chromium宿主验证 | 跨标签首写冲突、授权消费事务、实际IDB历史/Blob/hash、一致快照/包往返 |
| 外部协议/身份/安全 | 复用现有网关/Adapter捕获 | 实际request/action/原target/头来源，未知无自动submit，服务不写业务数据 |
| UI/交付/人因 | 实际正式入口任务，复用稳定helpers | 同动作DOM+网络+IDB+ZIP和真实截图；播种不代替空白人工主链 |
| 控制守卫 | 既有受测root反向探针 | 隔离副本变红，真实state不被临时改写；报告并写不误判产品业务落盘 |

类型保障只针对实际登记/emit的Module及消费者；strict/include关闭范围如实说明，不将“新TS存在/语法合法/读到依赖”写为迁移完成。构建入口以**实际emit文件集合**防漏列，不仅从少数root fileNames推测；不能生成了未纳管的依赖JS却继续让浏览器运行旧手写JS。改变源集同时更新jsconfig、构建/新鲜度规则、浏览器import、Docker排除及实际运行闭包；不新增第二编译/打包平台。

### 7.2 消费者可见反例（复用优先）

- 两标签同一所见摘要竞争：同授权版本+Shot只有一个pending登记/上游submit；另一方明确被消费/冲突。单标签双击和刷新后再点击也按同一消费证据。
- 摘要hash或实际消费头在异步字节读取期间变化：外发计数0；无关Shot变更不误阻塞。不能只把旧Snapshot再比较一次。
- 先登记存储失败/配额不足：外发计数0；外发成功后结果保存失败：不宣称未外发，恢复保留Unknown/原身份。
- 开A发起执行→切B→A返回：A的原action/候选保存，B的选择/状态/焦点不变；旧finally不清B锁。
- 首次人工采用seenVersion=0竞争、改选与导出重叠：冲突不覆盖，导出要么来自一份完整快照要么拒绝，无混合manifest/字节。
- 成功生成/打开比较/人工采用/导出且未点AI：复核外呼0，真实确定性报告仍存在；清单not_run，不伪造PASS。
- Unknown/task原目标与切模型并存：仅原target status/result，submit为0；同步即时返回只消费一次submit、无伪task。
- 完整项目包导出时另标签编辑：项目/文档/资产来自同一事务；导入后记录与字节一致，不只ZIP非空。
- 同版本生成的JS搬Implementation/改名：行为继续成立；源码钉删除后，恶意重复submit/OCC省略/错误字节仍被既有行为判据抓住，而不是降低成“未抛错”。

确认即提交的宿主证据必须关联**本次授权document/version+Shot+action**和实际请求增量；不能拿库里任意旧attempt行或总行数增长通过。共享前置需要既有正式UI helper适配新动作，不保留每Slot都确认的历史必经顺序。

### 7.3 执行成本

施工期按计划§15.3：同一连贯包编辑期间不反复build/全测；包结束一次类型/生成一致性、相关既有行为判据及一条实际改变路径。接线与模块移动用实际smoke，不新增结构/复制/wiring测试。最终R7.1的两轮在整合完成后执行，不能省也不提前变成日常工作。

失败保留首次证据，定位机制后修复并重验受影响行为；基础设施失败与产品错误分开，不用重跑洗绿。真实上游只在协议/品质确需证据且额度/授权成立时调用；本次设计轮不调用，也不为重构重复付费链。

