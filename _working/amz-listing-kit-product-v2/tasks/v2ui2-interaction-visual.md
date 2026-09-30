# V2.UI.2 前端交互契约与视觉基线 任务书

> CONTROL-STATUS: draft · AUTHORITY: task-brief（V2.UI.2 施工任务书；不发布目标、状态或规范）

仓库：E:\workbuddy_workspace\2026-09-20-16-38-19\amz-listing-kit（Windows PowerShell，命令先 Set-Location 到该目录）。
本任务书是 V2.UI.2 施工的唯一指令来源。上位契约：计划 §9.19b / §9.19c 与 §2.1 增补文本；先读计划 §5 工作流、
`app/product_v2/` 现存实现（index.html / styles.css / app.js / workspace.js）、`tools/v2_test_server.py` 与
`src/providers/v2_registry.py` 的 fake 场景变量、`_working/amz-listing-kit-product-v2/state.md`。
`out/` 下的历史草图不受控，只可参考，不作完成依据。

## 结果（完成定义）

1. 交互契约落盘 `docs/product-v2-ui-contract.md`，并登记进 `docs/INDEX.md`。
2. 视觉基线在正式入口 `app/product_v2/` 以真实 HTML/CSS/JS 可走查：真实状态驱动，fake provider 只替代模型调用。
3. 产品发起人（用户）在真实页面走查并明确确认「信息层级 / 主操作 / 图片比较 / 视觉方向」；未确认不算完成。
4. 证据写 `evals/product-v2/v2.ui.2-interaction-visual-<stamp>-final.{txt,json}`，
   截图写 `evals/product-v2/evidence/v2.ui.2-interaction-visual-<stamp>-*.png`（含关键特写与 390px、200%），
   走查记录（逐项确认/异议/修正结论与时间戳）并入最终证据。

## 边界（不做）

- 不改领域对象、状态机、Provider 语义、IndexedDB 所有权、服务端 API 合同与既有数据格式。
- 不引入新的运行时依赖、CSS 框架或构建步骤（选型门禁）。
- 不把演示商品、假状态或 fixture 内容写进产品入口；状态必须来自真实 repository/domain 记录与转换，
  fake provider 只替代外部模型调用，错误/部分失败/Unknown 由确定性场景注入而不是 DOM 伪造。
- 不新建第二套“演示页面”；设计与实现都落在正式入口。
- 不夹带 V2.5.5 未提交实现（处置见下）。

## 开工前置：V2.5.5 WIP 处置

工作树现有 V2.5.5 浏览器侧未提交实现：`app/product_v2/domain/suite-review.js`（未跟踪）与
`domain/{index,review,shared}.js`、`workspace.js`、`index.html`、`styles.css` 中的 V2.5.5 hunk。
开工第一步：把它们原样存档到 `_stage-amz-control/v2.5.5-wip-<stamp>/`（文件拷贝 + `git diff` patch +
未跟踪文件清单 + 一页 README 说明）。此后 V2.UI.2 的改动与提交不得包含这些 hunk；`domain/suite-review.js`
保留在工作树，不删除、不改写。V2.5.5 服务端（`src/providers/v2_suite_review*.py`）尚不存在，不在本任务范围。

## 交付物 A：`docs/product-v2-ui-contract.md`（先做，缺一不可）

- 六阶段信息架构（固定）：项目首页 +「资料—理解—方案—生成—审核返工—交付」；每阶段写清目标、
  完成条件、默认展开内容、完成后的短摘要。
- 逐视图契约：对象 / 信息（默认展示 vs 按需展开）/ 行为 / 状态 / 规则 / 反馈 / 导航。
  每个按钮必须写：为什么需要、前置条件、点击结果、失败反馈、下一步。
- 全局规则：同一时刻唯一视觉主操作；生成与审核以图片为中心；Prompt、hash、action/task id、provider
  身份等工程信息默认进“详情”但可查看可复制；保存状态与上游失效（STALE）如何投影。
- 表现层基线：CSS token（颜色/字级/间距/圆角/边框/阴影/焦点/状态色）与可复用组件状态清单
  （按钮/输入/卡片/列表/tab/进度/错误/空态）；正常文本与控件对比度、48px 触控目标、可见 label、
  语义 form、`:focus-visible`、逻辑 tab 顺序为最低要求；不用内联样式。
- 状态清单（最少）：空白首页、已有项目、资料缺失、理解异常/低置信、方案编辑与依赖阻断、生成中、
  部分失败、Unknown、候选比较与返工、交付阻断、存储/能力错误。
- 与计划 §9.19b 布局合同、§2.1 增补文本逐条对应，不得降级；INDEX 登记为 `设计草案`（生效条件：
  走查确认后转 `架构设计`/`current`）。

## 交付物 B：正式入口视觉基线（`app/product_v2/`）

- 首页：空/列表/创建中/导入失败/存储能力失败五态；紧凑产品栏 + 有边界主内容区；空状态只放
  “新建项目”主操作与“导入项目”次操作；不用装饰色带、大面积留白、placeholder 代替 label。
- 工作台：仍是一页；六阶段进度导航；默认只展开当前任务，已完成阶段显示短摘要并可回看；
  次要动作降级为普通按钮或菜单；同一时刻一个主按钮。
- 生成、比较、返工以图片画布为中心，规则结果紧邻对应 Shot；工程信息进“详情”。
- 既有能力不删除：槽位增删确认、套图增删排序、Style/Shot/Prompt 编辑、生成前确认、批量生成、
  Unknown 核对、比较、返工、采用在新结构中仍可达（允许先做粗投影，V2.UI.3 收口）。
- 新增 `tools/verify_v2_ui_2_interaction_visual.py`（编号 UI2-01 起）：静态守卫 + 浏览器走查
  （首页五态、六阶段代表状态、1440 整页与关键特写、390px、200% 缩放、键盘路径、零意外 console/network）
  + IndexedDB 后置条件。
- CI 必须保持全绿：被合法 DOM 重组影响的既有验证器按“语义/状态断言”迁移（不删断言、不放宽）；
  `app/server.py --check` 与全部既有验证器继续通过。每次推送前跑 `tools/check_docs.py --no-run`
  与 `tools/check_project_state.py`。

## 交付物 C：产品发起人走查（确认门）

- 走查脚本：首页 →（空白）新建 → 资料 → 理解 → 方案 → 生成（含部分失败/Unknown）→
  审核返工（比较/返工/采纳）→ 交付（阻断与就绪）→ 错误状态 → 390px 与 200% 缩放。
- 在本地正式入口 + fake provider 的走查服务上进行（localhost 是安全上下文；provider 与场景变量以
  `config/product-v2/providers.json`、`src/providers/v2_registry.py` 为准）；远程 HTTPS 入口保持可用，
  不作回归破坏。交付给产品发起人：可点击的走查地址 + 证据截图清单 + 逐项确认表。
- 走查记录写进最终证据：逐项确认或异议、被否的具体界面元素、修正后复看的结论与时间戳。
  产品发起人未明确确认前不得把任务置 done，不得开始 V2.UI.3。
- 红线：任何“需要旁边解释才知道点哪里”、工程字段压过业务信息、关键操作被遮挡、仍像一长条调试表单，
  都算未通过。

## 允许改动

- `app/product_v2/index.html`、`styles.css`、`app.js`、`workspace.js`（重组与投影；不新增状态源）；
  必要时新增 `app/product_v2/ui/` 下的纯表现模块。
- 新建 `docs/product-v2-ui-contract.md`；`docs/INDEX.md`、计划 §9.19b 的证据登记；
  `tools/verify_v2_ui_2_interaction_visual.py`；受影响验证器的断言迁移；`README.md` 验证入口；
  `_working/amz-listing-kit-product-v2/state.md`；`evals/product-v2/**` 证据。
- 不动：`app/product_v2/domain/**`、`app/product_v2/storage/**`、`app/product_v2_server.py`、
  `src/**`、`config/**`、`deploy/**`、`.github/**`。

## 完成与回退

- 完成条件：A 落盘并登记 → B 证据生成 → C 走查确认 → 契约转 `current`、state 置 done、
  计划 §9.19b 登记证据。
- 回退：未确认只改契约与表现层，不进入 V2.UI.3；领域对象与既有数据不动；按 Git 提交边界恢复。

## 硬约束

- Python 一律 `uv run --locked python ...`；行尾 LF；中文补丁走 codex.exe：
  & 'C:\Users\31368\AppData\Local\OpenAI\Codex\bin\7537f22ba194f7c1\codex.exe' --codex-run-as-apply-patch ($patch.Replace("`r","").TrimEnd("`n"))
- 不提交 V2.5.5 未完成实现；不夹带其它任务 hunk；截图只放 `evals/product-v2/evidence/`，
  dev 迭代证据用 `-devN` 后缀不提交。任何卡点直接发消息给 root。
