<!-- 拆分件：不变约束、质量与上下文路由 -->
> [product-v2-project-context.md](product-v2-project-context.md) · CONTROL-STATUS: current · AUTHORITY: project-context
> 原文第 291–329 行 · [前片](product-v2-project-context.vendor-and-module-map.md)

## 6. 不变约束

1. 模型输出是候选，不是事实、决定或完成证据。
2. 未确认商品事实不得进入带事实断言的图片方案和 Prompt。
3. 用户可以查看和修改完整 Prompt，但主路径不要求用户从零编写 Prompt。
4. 参考图、候选、历史 Prompt、返工结果和导出版本不被静默覆盖。
5. 修改事实、StyleSpec、ShotSpec 或 Prompt 必须按依赖范围使下游版本失效。
6. 一次 Shot 返工不得改变无关 Shot 的候选、任务身份和选择。
7. 外部调用超时是 `UNKNOWN`，不是失败；已知 task ID 先核对再决定是否重试。
8. VLM只提出可选建议，人工决定采用；硬规则来自可复现的确定性检查。无AI报告不强制付费复核，准确交付政策唯一在计划§14.8。
9. 主流程不需要主体分割或抠图；抠图仅可作为未来独立、显式选择的专项能力。
10. 服务器不保存用户项目状态；浏览器清理数据或 origin 变化造成的迁移由项目包解决。
11. 默认密钥只在服务器；三用途 BYOK 仅当前标签页内存/HTTPS 请求级，秘密不进持久化、Git、包、日志、错误或证据。理解、生图、复核各有有限 Provider/key 头，共用有效配置和错误边界；默认档缺省 closed，运行权限仍以实际配置及计划为准。
12. 远程正式入口必须来自可信 HTTPS secure context；本机 localhost 是唯一明文开发例外。
13. 桌面主场景的界面投影业务任务，信息与滚动层级按设计§13.3；Prompt/hash/task等内部信息按需可查而不常驻，不以“可追溯”要求普通用户阅读工程结构。

## 7. 质量门槛

| 层 | 必须证明什么 | 主要证据 |
|---|---|---|
| 控制面 | 产品Goal/依赖、工作规则、Issue/PR、产品权限/恢复各自归属清楚；最新修订可从冷入口找到，不被旧指令覆盖 | `tools/check_docs.py`、`tools/check_project_state.py`、`tools/refactor_resume.py`及不带聊天背景的读取核对；通过不等于产品完成 |
| 领域与存储 | 当前 schema、事务、依赖失效、Blob 生命周期与同版本往返正确；旧版本兼容按 SEL-018 不要求 | 单元测试、反向探针、导入/导出哈希比对 |
| 服务合同 | 无服务器业务持久化；错误、Unknown 与 Provider 身份可恢复 | API 契约测试、服务器重启轨迹、磁盘差异审计 |
| 浏览器产品 | 正式入口以真实内容走通人工/辅助、比较/恢复/导出；普通用户动作、视觉层级、认知负担、精确对象与反馈/恢复可用；长内容和实际视口/缩放/键盘不破坏关键操作 | 计划§14.9任务、真实画面/动作、浏览器请求/IDB/ZIP；具体缺口须工程修正，不以草图/空数据/自动化绿灯代替 |
| 生成系统 | 普通输入由程序形成协调视觉简报，并与事实/准确文案/图序一致；实际Prompt来源、原action/request/task与原候选可追溯 | 设计§13.9；编译稿与专家人工稿分开，核实际出站及原像素。HTTP/schema/hash正确或人工稿成功不证明程序稿品质 |
| 工程与真人验收 | 工程主链及显著人因问题按计划§14.8–14.9/§10与当前修订直接闭合；独立首次使用另列 | 工程画面/操作/成品不由C15/C17替代；C15/C17本轮之外且未发生，不冒充通过，也不据此将可达设计修正无限后置 |
| 格式检查 | 暂无 ruff/eslint：本仓库没有格式化工具链，格式由 `.gitattributes` 与评审保证 | 引入格式化工具需先过选型门（SEL 记录） |
| 静态检查 | 采用SEL-021的渐进TypeScript：已迁 Module 以 `.ts` 源做 strict 检查，保留的 JS 逐个 `// @ts-check` 自愿纳入（errors.js/invalidation.js）；`npm run check:types` / `npm run build:frontend` / `npm run build:frontend-node` 与 tsconfig include 是实际覆盖 | 不将node语法检查、选型批准或历史绿灯写成当前全仓类型通过；jsconfig `checkJs` 关闭是覆盖范围声明，被依赖拉入但未列出的 JS 不在保障内 |
| 行为验证 | 原生node领域行为与Python合同/宿主验证分层，按计划§7.3及实际已接线入口 | 行为/边界/转换与IDB/网络/浏览器后置分工；规则见AGENTS，不因规约修订新增验证框架 |
| 覆盖率 | 暂不设阈值：本项目的判据是“证据能判红”，不是行覆盖率 | 若引入覆盖率门槛，先立 SEL 决策并说明理由 |
| 应用构建 | Vite 标准构建唯一产物 `dist/product-v2`（`npm run build:frontend`），信封校验器由 `npm run build:envelope` 从 `src/providers/v2_image.py` 生成进 `domain/generated/`（gitignored，不提交）；正式入口只服务构建产物，生产无 Node/编译器、无 TS 源码回退 | `python app/server.py --check`、`npm run build:frontend`、`docker build` |
| 容器交付 | 区分现有完整事务实现、stage替身证据与当前实际Docker/HTTPS发布结果；healthy不代表页面可用 | 计划§7.7/R7.4及详细设计§11.5；真实镜像origin页面、可信HTTPS/资源/主链、服务回退及同origin数据恢复分别证明，规划不运行发布 |

## 8. 上下文读取与写入路由

读取顺序与写入路由的**唯一权威**在 [`docs/INDEX.md`](INDEX.md)（§1 的恢复读取顺序、§5 的
「写入路由：改哪里，不改哪里」）。本节不再复制这两张表：两处都写、内容一致时它们仍会
各自漂移，读者也不知道该信哪一份。本文件回到自己的问题——项目是什么、怎样运行、
数据归谁、目录与质量门槛是什么。
