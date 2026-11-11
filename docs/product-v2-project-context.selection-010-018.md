<!-- 拆分件：选型 SEL-010–018 -->
> [product-v2-project-context.md](product-v2-project-context.md) · CONTROL-STATUS: current · AUTHORITY: project-context
> 原文第 111–119 行 · [前片](product-v2-project-context.technology-selection-000-009.md) · [后片](product-v2-project-context.selection-019-025.md)

<!-- 续接：原选型表从前片 SEL-009 后继续；本标记、续接标题与重复表头在重组时移除。 -->
### 4.1 选型记录（续：SEL-010–018）

| ID | 范围 | 决策 | 被拒方案 | 复访条件 |
|---|---|---|---|---|
| SEL-010 | 图像网关传输层 | 复用 `requests`（V1 已在用的锁定直接依赖）+ 三条无状态路由（submit / status / result）；协议与错误映射按 §9.10 自写，但请求形状沿用 V1 冻结合同（`src/providers/dashscope_image.py`）；PoC 与依赖实测见 `evals/product-v2/sel010-image-gateway-transport-poc-20260930.txt` | 官方 `dashscope` SDK（0.27.x→1.27.7 实测解析 32 包，拖入 aiohttp / typer / websocket-client 等）；`httpx`（第二套 HTTP 客户端，无协议收益）；OpenAI 兼容图像端点（百炼图像合成不是该形状） | 需要批量并发、取消、多供应商路由或成本统计时重估 SDK；百炼改协议时按冻结合同重测并更新 §9.10 |
| SEL-011 | 复核（VLM）通道与模型 | 用户已定（2026-09-30）：复核复用 SEL-003 的 langchain 通道（`ChatOpenAI` + json_mode 结构化输出 + `map_openai_exception` 四归口），默认模型 `qwen-vl-max`（`REVIEW_MODEL` 可覆盖，registry 条目 `dashscope-review`）；输入 = 候选 + ≤3 参考图 + ShotSpec 摘要 + 已确认事实；输出只允许 7 个 check + evidence + confidence；VLM 只提示、不得 BLOCK、失败落 Unknown、不产生采纳 | 新建第二套 HTTP 客户端/适配器层（重复造轮子）；官方 SDK（拖包）；让模型自带严重度或采纳结论；把审美判断升级为平台硬阻断 | 需要多模态模型路由/降级或成本统计；百炼模型命名/能力变化；检出质量校准需要模型对比时（后续任务） |
| SEL-012 | 浏览器支持与安全 origin | 用户恢复后的当前 Goal 验证范围为稳定版桌面 Chrome（计划 §2.4）；旧 Chrome/Edge 专项记录保留历史身份，不宣称 Edge 本轮通过。远程正式入口必须是可信 HTTPS secure context，TLS 由现有穿透/反向代理终止，应用容器保持无状态 HTTP。保留 IndexedDB + 原生 WebCrypto；不为明文 HTTP 自研 UUID/SHA-256、密码学 polyfill 或服务器项目存储；失败区分能力/schema/配额/事务并给恢复动作 | 浏览器手写密码学降级、服务端项目库、把所有宿主纳入保证范围、用无头结果替真人走查 | 当前 Goal 的浏览器范围或实际受控宿主需求改变时重开；先证明真实约束 |
| SEL-013 | 可访问性扫描 | 用户已定（2026-10-01，自审授权范围内）：vendor axe-core 4.13.0（MPL-2.0）单文件到测试侧 `evals/product-v2/vendor/`，由 `tools/verify_v2_6_4_accessibility.py` 注入正式入口页面运行扫描；不新增构建链、不进产品运行时 | 运行时 CDN 引入（不可离线复现）；npm/pip 构建依赖（违反 SEL-000 无构建链）；自写规则引擎（重复造轮子） | axe 上游大版本升级（重跑可访问性终验）；MPL 许可变化；需要运行时无障碍报告时重估 |
| SEL-014 | 重构运行形态与模型范围 | 用户确认：浏览器本地优先 + 无业务持久化 Python 网关；模型不是核心卖点，仅有限模型解耦；第二生图已锁定大陆火山 `doubao-seedream-5-0-flash-260915`（R4.1 锁方向 / R4.2 真链 / R5.2 同步 Adapter `v2_volcengine_image.py`），`providers.json` 双 image 条目 `dashscope-image` + `volcengine-ark`，不迁 Node 或引入服务端项目库 | 胖后端/账户数据库、全栈 TS、任意模型平台、仅换 model 字符串冒充生图兼容 | 跨设备/协作/后台持续执行成为实际需求，或有限协议维护成本实测不可接受时 |
| SEL-015 | 凭据产品政策 | BYOK 为主，部署默认档仅受限试用且缺省 closed。理解、生图、单图/整套复核共用 registry/credentials 的请求级有效配置；有限 Provider 选择与三用途 key 仅当前标签页内存及 HTTPS 请求，不进持久化/包/日志/错误/诊断；默认 key 不下发、不附到自定义目标。旧任务补原目标/来源凭据，不切新动作模型、不借默认 key 恢复 | 持久化 key、任意目标、Provider 业务分支、替旧任务补造当前身份 | 持久化凭据、账户/云同步或新增供应商协议需求时另获授权 |
| SEL-016 | 前端工程化与 UI | 用户确认渐进类型检查/验证分层与 UI 人体工程审计方向；先实际任务基线，再原型和目标合同；复用已有业务语义但不将现有 domain/repository 或页面结构设为不可替换；不预定布局、六强制步骤、React/Vue、构建工具或全仓 TS；按 SEL-018 允许激进 clean cutover | 先换皮/拆文件、框架即工程化、机械降低点击而取消必要确认、Skill 代替真页面证据 | V2.R2/R3.1 的问题/原型/PoC 提供明确收益时选择工具与布局 |
| SEL-017 | Goal历史与当前绑定 | 真实产品Goal绑定/原生观察只取state，原生全文取计划§2.1，最新用户修订取§17.13；旧2026-10-05/07与独立规划仅保留原范围。新会话核对真实返回，不在上下文固定另一份当前ID/预算/进度，不重复创建或伪称原生正文已改 | 旧ID承担新正文、假生命周期、双计划/进度、规划/规约完成冒充产品完成 | 新会话或目标变化时按INDEX核对实际返回与最新用户修订，再同步绑定/受影响状态；未明确恢复则保持停工 |
| SEL-018 | 开发态兼容与设计自由度 | 用户明确：“不用考虑历史兼容性，现在仍在开发阶段，允许你做激进的设计。”旧版本/schema/包迁移及真实旧工件恢复不再要求；按计划 §2.3 clean cutover，可重做 Module/Interface/UI/记录格式、移除被替代路径；新开发库/旧格式拒绝须显式，不静默删除浏览器数据。同版本候选历史、人工选择、任务冻结身份、刷新恢复、ZIP哈希及安全不变量保留；其余权限门不变 | 为缺失旧测试包停工、保留向后兼容 shim/迁移层、将激进设计当作静默丢数据或付费/部署/V1删除授权 | 首次正式发布/存在需支持的历史用户数据时，重新定义版本兼容承诺；开发期不预建设迁移层 |

<!-- 续接：原选型表在 product-v2-project-context.selection-019-025.md 从 SEL-019 接续；此标记在重组时移除。 -->
