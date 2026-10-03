NOT-AUTHORITY: point-in-time UI audit evidence; not a plan, current state, release acceptance, or human walkthrough.

# V2.R2.1 · Chrome 实际页面任务基线

## 范围与权限

正式 product handler 与真实 ESM/IndexedDB/UI，经本地测试服务器装配四类 fake Provider；商品为已有授权 `examples/input/cup_source.jpg`，输入“白色保温杯”。不调用真实模型、不产生费用、不向供应商上传、不提交推送、不部署。自动化不是 C17/C15。

用户最终授权仅 Chrome 无头、独立临时配置与测试数据、浏览器接口页面内输入；禁止 Edge、可见窗口、抢焦点、系统级键鼠和日常配置变更。授权见 `background-automation-20261001.md`，权威落点为计划 §3。此前自行启动的 Edge 与可见测试 Chrome 已关闭；旧观察保留历史身份，不充当新的无头覆盖。当前 headless Chrome 版本 `154.0.8037.93`，独立配置初始数据库为空。

“审计记录完成”不等于七条业务能力全部通过。T7 是实测能力缺口；Edge/桌面专项未执行，真人理解/易用性未验收；启动间歇缺陷仍开放。本次未改产品来掩盖基线。

## 七任务实际轨迹

执行顺序 T1→T4→T3→T6→T2→T5→T7，非按编号伪装时间顺序。原始记录/事件、每次 DB 状态、网络与 console 后置：`ui-baseline-20261001-chrome.json`。

| 任务 | 实际路径与观察 | 证据范围/未证明项 |
|---|---|---|
| T1 空白到候选 | 新建→打开→文件输入上传参考图→填写资料→分析→逐项确认关键事实→推荐方案→四张 Prompt 编译→明确确认→生成四候选 | fake 图像，只证明页面业务路径；70 个事件中 17 click、19 scroll，非真人耗时/认知指标 |
| T2 改事实继续 | 将 `signature_features` 标未知；下游入口被门禁阻断；重新填值并人工确认后进入生成，四张 Prompt 为 stale、就绪 0/4；原成功 Attempt 保留 | 正确保留旧结果；继续流程仍需逐张处理失效 Prompt，未以旧确认直接重提 |
| T3 比较/采用旧图 | 主图返工产生 v2 后，从比较面板选择 v1→打开采用确认→明确采用→查看持久 selection | selection 引用旧候选 `act-0f510b88d55a4595870718039abb8d5c`；并非自动取最新；未证明模型质量 |
| T4 单图返工 | 主图“按问题返工”→填写方向→预览→确认生成→新候选保存 | 前后无关 Shot 记录比较为 true；其余三个 Shot 未被返工改写 |
| T5 partial/Unknown | 本地 fixture 的新 action 依次成功、明确失败、有 task 查询未知、无 task 提交未知；逐个使用实际页面动作核对 | 成功候选保留。已知 task 后续核对恢复成功，submit 数 9→9，无重复提交；无 task 分支不假造查询成功 |
| T6 刷新/重开/导出 | 刷新前后记录一致；本地 fake 服务重启前后记录一致；UI 产生项目/交付 ZIP；新临时 Chrome 配置导入真实项目包，再捕获实际下载并校验字节 | 项目 58 文档/6 资产。两个实际下载成功、CRC/图片 SHA256 校验通过；发现旧候选交付 Prompt 溯源不一致，见 B01，因此交付可追溯性不通过 |
| T7 换设置/旧任务/新任务 | 检查当前产品控件与 capabilities | **缺口**：没有模型/凭据/endpoint 设置入口，不能实际完成换设置核对旧任务与向新模型提交；不以直接改 JSON 或假开关冒充 |

T1/T4/T3 的事件数组为同一页面累计快照，不把 17/21/25 次 click 相加或当作各任务独立开销。T2/T5 在刷新后另起轨迹。选择器错误、工具超时与人工思考时间不计作用户误点/停顿；真实用户的记忆负担、误点率、思考停顿和语义理解仍待真人走查。

T5 的临时注入装配是现有 `FakeImageProvider(size=1200)`：新 submit 按计数 `%4` 选 `ok/failed/status_unknown/submit_unknown`，按 `task_id_for(action_id)` 保存内存场景映射；status 复用该映射。控制切回 ok 后，已有编号可核对成功，不增加 submit。其余三个 factory 为 fake semantic/review/suite-review；没有 provider 凭据或外部业务落盘。采集完成后停止自建服务，清除临时 launcher/control；原始轨迹、截图与下载保留为证据。

## Chrome 环境与页面内键盘

当前授权后重新执行的无头证据：`headless-matrix-20261001.json`，截图在 `r21-assets-20261001-1445/headless-*.png`。

- 1440×900、1366×768、390×844，分别检查资料、理解、审核比较，共 9 个 surface。当前 `scrollWidth` 等于 viewport 宽，不据此泛称全部内容无遮挡。
- 独立临时配置中的 Chrome 设置页面选择真正 125%/200% zoom；未用 CSS transform 或 pinch 冒充。1440 基础宽实测 1152/720，1366 基础宽实测 1093/683；DPR 1.25/2、visualViewport.scale=1。两宽×两 zoom×三层共 12 个 surface。
- 无头 `Browser.setWindowBounds` 首次不能校准布局，记录该工具条件，改用浏览器 viewport metrics 建立 100% 基准后再用 Chrome 设置实际 zoom；不是修改用户日常配置，没有可见窗口/系统输入。
- 三层共 54 次浏览器 Tab；比较面板 ArrowRight 使焦点与选中候选 ID 相同，Escape 返回“比较候选（2）”触发控件。其他采用面板 Escape 及 390px 控件可达观察保留于原始轨迹。
- 这不是“陌生人纯键盘全链已通过”；没有真人读懂、系统对话框、浏览器工具栏操作或 Edge 矩阵的覆盖。
- Chrome 控制台/页面错误采集均为空；网络 151 条在原始后置中，执行目标为 loopback。空 console 不证明不存在 UI/溯源缺陷。

## 分级问题与下一动作

| ID/级别 | 可证伪的对象/现象 | 处置任务 |
|---|---|---|
| B01 发布 blocker | T3 采用旧主图 v1，其原 action 冻结 Prompt v1/hash `228457c96d7cf325a376cd2fb3240eac0cd4ce508949426b1d8d97466d4b7d12`；实际交付 manifest 同一 candidate/action/asset 却记录当前 Prompt v2/hash `a4461623862f4d4c3ca44429aeb278f2d3ac4d967f6783f398e62cf81f1b8fe6`。另外三张与原 Attempt 一致。字节没丢，但溯源错误，RC18 不能 proven | R6.3/RC18：必须从被采用候选的原执行身份取 Prompt，后续消费者行为回归；本次保持原 baseline |
| G01 能力缺口 | 当前模型设置/凭据入口缺失，T7 不能执行；不能证明跨设置/缺凭据/旧任务原目标恢复 | R4.3/R4.4/R6.3，先批准真实模型/协议/预算，离线假路径不当作真实兼容 |
| H01 高频继续劳动 | T2 一处关键事实重确认后，四张 Prompt 全 stale、就绪 0/4；用户仍要到生成层逐张处理，成功历史保留是正确安全语义 | R2.2/R6.1：显示失效原因、受影响范围与明确下一动作；不取消必要确认、不自动付费提交 |
| H02 图片上下文/滚动 | 1440 审核展开比较页高 3647px，390 高 4593px；比较在整套卡片和一致性检查之后，参考图 96px、候选缩略图 162px。截图可见参考/候选/采用上下文纵向分离 | R2.2/R6.2：保留同 Shot 图片上下文，实测比较/返工/采用导航；[INFERENCE] 增加记忆成本，尚无真人定量 |
| H03 技术词与异常分支 | Unknown 页面可见 provider 错误码、action、“新建 action（放弃核对）”；有编号与无编号分支正确不同，known task 核对不增加提交 | R2.2/R6.3：将状态/恢复含义与技术详情分层；保留显式放弃核对的风险含义，不自动重提 |
| V01 缩略图/长卡视觉 | fake 候选是纯色测试图；大预览卡、长技术/风险文本和小参考图可见，390 页很长；自动测量只证明可达/尺寸，不证明真实商品对比质量 | R2.2/R6.2，后续授权真实图与真人走查；不凭改色或截图宣称改善 |

五次关键事实确认有业务必要；不能仅为减点击删掉确认。采用与提交确认也是业务授权，不能因为原型简化就自动完成。

## 实际 ZIP 下载与完整性

新配置 headless 导入/下载/刷新 smoke 返回 exit 0：`headless-export-20261001.json`。实际下载保存在 `r21-assets-20261001-1445/headless-downloads/`。

- `project.zip`：402518 bytes，格式 2，SHA256 `695b84e60ac586c2d31ecbd89cb101bdfb0d379cce68bf0b796b8c39a72f69b0`。
- `delivery.zip`：48070 bytes，SHA256 `eff726836df7832a6e368607258516f90fcb20988bf709ebae186f5ab23a2e96`。
- 两包 CRC 正常；项目 6 资产与交付 4 图片字节哈希全部匹配。原 Attempt 与 manifest 对照发现 B01：1/4 Prompt provenance 不匹配。结果见 `headless-package-integrity-20261001.json`，不把脚本 exit 0 误当成 provenance 全过。
- 早期 managed 下载 helper 的 busy/cancel 与一次 Eval VM 超时属于自动化工具限制；没有据此判产品导出失败。独立无头 Chrome/Playwright 的实际下载已补证。最终 headless 缩放/尺寸/键盘 smoke exit 0，12+9 surface / 54 Tab。

## 尚未证明

真人 C17/C15、Edge/桌面专项、真实第二模型、费用/质量、T7 跨设置能力、启动间歇根治及最终 RC01-RC20。主图旧候选交付 Prompt 溯源已被反例否证。审计允许进入问题导向研究/原型，不允许发布或 Goal 完成。

## 控制面验证

本轮串行执行 `check_docs.py --no-run` → `check_project_state.py` → `evals/probes/project_state.py` → `evals/probes/docs_index.py` → `refactor_resume.py`，整链退出码 0。状态探针 56 向、路由探针 12 向一致，并逐字节还原；冷恢复输出 active / 8 阶段 / 26 任务 / next `V2.R2.3`。`check_docs --no-run` 不证明文档列出的产品命令实际执行；真实页面/下载/缩放证据由上述独立 smoke 提供。控制面全绿也不消除 B01 或替代 RC01-RC20。
