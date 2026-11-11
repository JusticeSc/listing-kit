<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/packet09-history-archive-20261007T085222Z.md -->
# 3. INDEX 引用逐条去向（登记表 65 行 + 正文引用）
[返回 packet09-history-archive-20261007T085222Z.md](packet09-history-archive-20261007T085222Z.md)

## 3. INDEX 引用逐条去向（登记表 65 行 + 正文引用）

- 登记表 65 行：逐行 `git ls-files` + 磁盘存在性核对——**全部存在，零断链**
 （`git -C amz-listing-kit -c core.quotepath=false ls-files 'docs/cards/*'
  'docs/standards-template/*'` 命中 cards 8 + templates 15；`ls-files | wc -l`=66 含根两份；
  check_docs 报“已登记 65 份，实际 65 份”全过即双向比对无增删）。
- 去向分类：现役 6（§2.1）/ 生成 8（§2.2）/ 草案 19（§2.3）/ 历史 32（§2.4）——
  登记状态与各文件头 CONTROL-STATUS 逐份一致（reader 侧 grep 27 命中 + shell 侧 ASCII 路径
  38 份一致；CJK 路径 11 份经 reader 复核一致，shell NONE 系引号转义假象）。
- 正文引用（§1 路由表 8 行 + §4/§5）：`docs/product-v2-project-context.md`、
  `docs/product-v2-refactor-plan.md`、`docs/product-v2-refactor-design.md`、
  `_working/amz-listing-kit-product-v2/state.md`、`README.md` 均指向现役（§2.1）；
  “旧计划/旧 state/drafts/standards-template 默认不读”指向历史/草案——定性正确，
  **无一处需修正或改标**。
- **不造假链接**：本片未新增/修改任何链接；存在性断言全部来自
  `check_docs --no-run`（退出码 0）+ `git ls-files` 输出，非推测。

## 4. 归档/移动/删除前置检查（搜索证据）

设计 §8 准入：“不得移动仍被权威引用的路径”。现役权威对历史材料的有效引用：

1. `docs/product-v2-refactor-plan.md:23` → H3（旧合同/C1–C17 来源）
2. `docs/product-v2-refactor-plan.md:24` → H21（旧进度/Goal 读数出处）
3. `docs/product-v2-project-context.md:124-125` → H3（SEL-000..013 操作设计出处）
4. `_working/amz-listing-kit-product-v2/state.md:86` → H21（R0.1 证据）
5. `_working/amz-listing-kit-product-v2/tasks/v255-verifier.md:24` → v255-server.md（同批任务书互引）
6. `docs/product-v2-refactor-plan.md:351,651` → C1 ui-contract（草案投影引用，非历史但同属“被引用不得移”）
7. `AGENTS.md:30-44,158,162,166` → C5–C19 及 C2–C4（采纳映射与技能条件引用）

grep 命令（仓库根 `amz-listing-kit/` 下执行，证据为本报告 §2–§3 所列 `path:line` 命中）：

- `grep pattern="goal-and-implementation-plan|drafts/|tasks/[a-z0-9]|implementation-plan-2026|requirements/state|product-v1/state|product-demo/state|v2-baseline/state" path={plan,context,design,ui-contract,README,AGENTS,state}` → 命中 plan:23/24、context:124-125、state:86、v255-verifier:24（其余为 INDEX 登记行与历史文件互引）。
- `grep pattern="ui-contract|agents/issue|agents/triage|agents/domain|架构设计|系统设计|…" path={plan,context,README,AGENTS,state}` → 命中 plan:351/651、AGENTS:42/53/158/162/166。

**结论**：7 组现役引用有效 → 32 份历史 + 19 份草案全部“有现役引用或登记链依赖”，
按指令“有现役引用则保留并列入报告”——**本片零移动/零删除**，改动清单为空（§6）。

## 5. 七闸门（逐条命令 + 退出码，真跑）

| # | 命令（`amz-listing-kit/` 下） | 退出码 |
|---|---|---|
| 1 | `node --check app/product_v2/workspace.js` | 0 |
| 2 | `npm run build:frontend`（EMIT 5 视图文件，tail 确认） | 0 |
| 3 | `npm run check:types`（`tsc --noEmit -p jsconfig.json`） | 0 |
| 4 | `npm run check:generated`（CHECK 5 视图文件） | 0 |
| 5 | `node --test evals/product-v2/node/*.test.mjs`（tests 227 / pass 227 / fail 0） | 0 |
| 6 | `uv run --locked python tools/check_project_state.py`（J4–J10 全过） | 0 |
| 7 | `uv run --locked python tools/check_docs.py --no-run`（登记 65/实际 65，全过） | 0 |

注：本片未触 `tools/**`、`app/**`、`src/**`、`evals/product-v2/node/**`；
闸门 1–6 结果与 sibling 包共用树状态一致，无本片引入的变更可归因。

## 6. 改动清单

- 新增：本证据文件 1 份（`evals/product-v2/refactor/packet09-history-archive-20261007T085222Z.md`）。
- 修改/移动/删除：**无**（理由见 §1/§4）。
- `state.md`：progress 与任务表未动，未追加归档说明（无搬迁发生，无说明可加）。
- commit：`git add` 仅本证据文件，信息含 `packet09`，不 push（见 yield 报告）。

## 7. 未决项

1. 登记计数口径：INDEX 称受管“根+docs+_working 全部 .md”，check_docs 报 65/65，
   而 `git ls-files docs+_working+README+AGENTS` 实际 66（含 INDEX 自身）。
   差 1 疑为守卫计数不含 INDEX 自身或含根方式不同——非本片引入，不改守卫，
   留待包09收口或守卫owner澄清。
2. CJK 路径 shell 测量假象：`for f in $(git ls-files …)` + `head` 在 win32 上对
   中文路径报 os error 123（引号转义），reader 侧 grep 同文件 CONTROL-STATUS 正常命中。
   后续脚本应从 git 侧取 `core.quotepath=false` 原字节或用 reader/grep 工具，勿据 shell NONE 判缺头。
3. 物理归档（如 `_archives/` 精确字节归档 + hash 核对 + 引用同步）需按设计 §8
   “只对有权限的过程材料执行”另立任务：先消 §4 的 7 组现役引用（改权威正文=改计划/context，
   须快照+用户确认），再出精确移动清单。本片不做。
