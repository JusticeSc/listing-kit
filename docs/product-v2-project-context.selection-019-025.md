<!-- 拆分件：选型 SEL-019–025 与结论边界 -->
> [product-v2-project-context.md](product-v2-project-context.md) · CONTROL-STATUS: current · AUTHORITY: project-context
> 原文第 120–137 行 · [前片](product-v2-project-context.selection-010-018.md) · [后片](product-v2-project-context.dependencies-python.md)

<!-- 续接：原选型表从前片 SEL-018 后继续；本标记、续接标题与重复表头在重组时移除。 -->
### 4.1 选型记录（续：SEL-019–025）

| ID | 范围 | 决策 | 被拒方案 | 复访条件 |
|---|---|---|---|---|
| SEL-019 | 问题导向参考系统研究 | V2.R2.3 已核查 pi `88ff80b`/0.99.2（MIT）、ComfyUI `2d6b7328`/0.38.0（GPL v3）、Open WebUI `8bd8b4f`/0.11.4（自定义品牌约束许可），固定全文 SHA/路径见 `evals/product-v2/refactor/reference-review-20261001.md`。仅采纳概念：用途/能力/协议 Adapter/凭据分层；交付只读采用候选原 action 的冻结 Prompt，不读当前编辑头；同 Shot 直接图片对照与稳定候选导航；Unknown 分身份恢复、状态/影响/下一动作先于技术详情。BYOK 仍仅内存，概念不等于新依赖或真实能力证明，布局由 R2.2 原型冻结 | 复制三套平台/代码/样式/品牌、账户或服务器项目库、pi 聊天兼容冒充图片协议、上游持久凭据照搬 IndexedDB、Comfy 元数据新功能、隐式自动重提/采用/付费、未选型新运行依赖 | R2.2/R4.1/R4.2 的原型/能力/费用证据；确需复制代码或引入库时重开许可/依赖门 |
| SEL-020 | 电商参考 skill 问题导向复核 | V2.R2.2 只读核查工作区根三目录：`ecommerce-image-suite-main/`（Apache-2.0 但 README 陈旧矛盾、占位符未填、模特/实拍无许可）、`ecom-details-image-main/`（自称 MIT 但无 LICENSE 文件，`.env.example` 含第三方代理明文 key 泄漏样本）、`ecommerce-skills-main/`（MIT 2026 dlazy，实读 platform-compliance/detect-task/item-detail＋shared 脚本/测试/规格）。结论：三者只提供流程编排与规格清单（批次 manifest、参考图锁定、先单图后整套、客观像素机检＋主观 VLM 质检分层、固定质检 prompt、中文排版四条件、逐轮 manifest、dry-run、不伪造测量），均无图片结果验收实现（保真/文字/事实/尺寸/齐全性须 amz 自建）；零字节复制，不复制代码/模板/样式/品牌/资产/凭据，不引入 Node 脚本链与真实调用/付费；证据 `evals/product-v2/refactor/prototype-review-20261002.md` §5 | 未经许可复制代码/模板原文、样式/模特/实拍资产、品牌与联系方式；硬编码供应商分支冒充解耦；真实模型调用/付费上传；把 prompt 自述或人工观感当验收结论；复用泄漏凭据 | R6 验收自建时复用 rubric/阈值数据；确需复制代码或引入依赖时重开许可/依赖门 |
| SEL-021 | 前端开发检查与渐进TS迁移 | 根manifest/lock锁typescript 6.0.3（Apache-2.0），安装禁scripts；Node24.19.0/npm11.17.0，行为复用node:test。已迁TS为唯一手工源码，保留JS调用方用逐文件@ts-check，实际覆盖取tsconfig.json；SEL-023现承接Vite浏览器产物，Node验证树用标准tsc emit到build/frontend-node，不再同目录生成JS或运行check:generated。正式静态入口拒绝TS源码，生产无Node/编译器；不承诺全仓TS或未纳入JS有类型保障 | 全仓TS强迁移、node --check冒充类型检查、compiler进生产、多份Implementation、any/忽略/假断言洗诊断、隐式npx取包 | 受影响owner/调用方实际类型与运行验证；新依赖另过门，撤销工具需同步源码/产物/配置/CI |
| SEL-022 | main基线HTTP替换（已确认，已采纳并进入main） | FastAPI 0.143.3（MIT）＋Uvicorn 0.54.0（BSD-3-Clause），直接Pydantic 2.13.5（MIT），不装standard extras。`app/product_v2_server.py`装配路由，`product_v2_http.py`负责ASGI生命周期/静态策略，旧HTTP实现退出；registry/credentials/outbound/Unknown政策保留。已随PR #13–#16进入main（历史依据见README与state当前基线），不再是本地候选。隔离PoC见`_stage-amz-control/main-baseline-execution-20261017/http-poc/http_selection_poc.json`，干净候选/镜像结论另取PR证据 | 手写HTTP层、async handler阻塞SDK、新旧server fallback、无关CLI/遥测SDK | 真实路由/TCP/Chrome/限额/退出及生产镜像需随对应变更验证，PoC不代签发布 |
| SEL-023 | main基线前端构建/渲染（已确认，已采纳并进入main） | 用户2026-10-17已确认Vite 8.3.4（MIT，dev-only）＋标准tsc及lit-html 3.3.3（BSD-3-Clause）；Vite传递含dev-only MPL-2.0 lightningcss。P4已切到标准Vite唯一产物`dist/product-v2`，旧同目录emit/check:generated退出；P5视图迁移使用lit-html，业务状态保持原owner、UI草稿只归视图。已随PR #13–#16进入main（历史依据见README与state当前基线）。实际进度/证据取state与#10，不把隔离PoC或已安装当正式验收 | 自建转译/打包器、React/Vue并用、第二全局store、产物回退源码、Node生产服务 | 正式清洁构建、Python静态入口/镜像资源及真实工作区任务通过；PoC不能替代正式视图迁移 |
| SEL-024 | main基线Python验证组织（已确认，已采纳并进入main） | pytest 9.1.1（MIT，dev-only）管理`tests/gateway`及`tests/dev`，已替换对应旧网关runner；CI/登记/选择器/聚合走`python -m pytest`，付费/远程/人工入口不在发现集合。已随PR #13–#16进入main（历史依据见README与state当前基线）。继续复用node:test与Playwright，未受影响入口不机械迁移 | pytest外套永久CLI、双runner、自动重跑、paid/remote/manual自动发现 | 正式首组需证明实际判错及退出清理；依赖或分类变化时局部重验 |
 | SEL-025 | main基线共享通信结构（已确认，已落地） | 结构权威 = `src/providers/v2_image.py` 的 `ImageWire*` Pydantic 模型；构建期 `tools/export_image_envelope_schema.py` 导出 JSON Schema，`tools/generate_image_envelope_validator.mjs` 用 Ajv 8.20.0（MIT，仅构建期 codegen）生成 standalone ESM 校验器 `domain/generated/image-task-envelope.validate.js`；浏览器唯一入口 `domain/image-envelope.ts`（类型投影见 `domain/type-contracts.d.ts`，分类/状态语义仍归 `domain/attempt.ts`）。`npm run check:envelope` 以 199 案例（真实响应 7 + 变异 192）证 Python↔JS 同拒（分歧 0、误放行 0），R52-02 要求 harness A20 结构门；dist 合同入口含 `generation.js`/`domain/attempt.js`，浏览器产物真实消费生成模块 | Zod第三份权威、全领域Schema化、浏览器动态eval、生成校验与旧镜像长期并行 | 真实非法输入同拒、脱敏错误、真实结构来源及净收益；不额外收紧业务合同换取PoC通过，不留下半成品 |

SEL-000..013 中对旧计划 §9.x 的操作设计引用仍指冻结的
`product-v2-goal-and-implementation-plan.md`，不把历史操作说明当未来任务。
SEL-014..021保存既有技术方向和固定来源；SEL-022..025已于2026-10-17 02:00:36Z获用户四项明确确认（会话`01a13065-2097-721b-9d1f-35bb099947f3`的ask原始答复），无需再次询问。确认后已随PR #13–#16采纳并进入main（历史依据见README与state当前基线），本表不再保留“本地候选/切换中”状态；当前依赖权威/实际运行仍取§4.2及代码。当前执行绑定与前沿取state，不据历史工程/发布授权施工。

状态：SEL-000 至 SEL-011 已定案（2026-09-30）。依赖权威已从 `requirements.txt` 迁移到
`pyproject.toml` + `uv.lock`，守卫、CI、README 同步（证据见
`evals/product-v2/dependency-authority-migration-20260930.txt`）；依赖按 SEL-003 引入
（langchain-core / langchain-openai）。现有文字、商品图文、生图及复核 Adapter 和客户端三用途设置已装配；
具体运行证明及尚未成立的验收看 README 与 state，不据复用库或模型名称宣称真实能力通过。

