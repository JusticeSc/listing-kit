<!-- 拆分件 03/03 · 父文档 evals/product-v2/refactor/asset-continuation-20261008.md -->
# 真实缩放与纯键盘覆盖（1440/1366/390 · 125%/200%）
[返回 asset-continuation-20261008.md](asset-continuation-20261008.md)

## 真实缩放与纯键盘覆盖（1440/1366/390 · 125%/200%）

证据：`evals/product-v2/refactor/asset-continuation-20261008-zoom.json` + `../evidence/asset-continuation-20261008-zoom-{1440,1366,390,125,200}.png`（均为真实 PNG，逐张核对过 IHDR）。方法：系统 Chrome `--headless=new` + 一次性 `--user-data-dir`（`omp-zoom-kbd-…`，采集后删除），本地正式入口 `http://127.0.0.1:8780`，用真实文件输入导入既有合法项目包，导入后整套报告过期→按真实用户路径点「运行本地确定性检查」重跑（v2.5.5 阻断 0 · 高风险 0 · 提醒 1 · 未知 0 · 视觉复核未运行（可选）），交付门禁转通过；缩放用 `chrome://settings/appearance` 的 Page zoom（真实页面缩放，等价 Ctrl+/-，非 CSS zoom/transform、非启动期 device-scale 开关）。

| 场景 | 布局宽度 | dpr | 关键操作 | 结论 |
|---|---|---|---|---|
| 1440×1000 @100% | 1440 | 1.25 | 交付ZIP/项目包均 enabled、在视口内、`elementFromPoint` 命中自身 | 可达不遮挡 |
| 1366×768 @100% | 1366 | 1.25 | 同上 | 可达不遮挡 |
| 390×844 @100% | 390 | 1.25 | 同上（left 33/right 179 ≤ 390）；文档无横向溢出（375=375） | 可达不遮挡；阶段导航行需横向滚动（550>345），符合“390px 只承诺关键可达不遮挡” |
| 1440×1000 @125% | **1152** = 1440/1.25 | 1.5625 | 同上；六个阶段按钮全在视口内 | 真实页面缩放成立 |
| 1440×1000 @200% | **720** = 1440/2 | 2.5 | 同上；六个阶段按钮全在视口内 | 真实页面缩放成立 |

纯键盘（200%，重新加载后 `activeElement=body`，全程只用 Tab/Enter）：焦点序列 `model-settings-open → back-home → 项目信息 → intake → understand → plan → generate → review → deliver`，在 `deliver` 按 Enter 切阶段，再到 `deliver-export` 按 Enter ⇒ 真实产出交付包 `正式开发—人工套图主链-交付包-20261008-0927.zip（30 KB）sha256 cb4bceff33a3040b…`；下一 Tab 到 `deliver-project-package` 按 Enter ⇒ “已导出项目包（含完整历史，可在别的浏览器导入）。”本文件只记应用层结果；ZIP 实际字节/成员/hash 的浏览器层证据由 `--page-smoke` 的 PS-07-package（真实 download 事件落盘并算 sha256）承担。明确模拟性质，不冒充独立真人 C15/C17；dpr 含宿主 1.25 显示缩放；未在远端 HTTPS 环境重复该几何。

## 第三次CI结果：全绿（控制面 + 真实镜像自检 32/32 + 离线回退 13/13）

候选`4847ed9`，[run 37758524774](https://github.com/JusticeSc/listing-kit/actions/runs/37758524774)：**两个 job 都 success**。上一轮的 -04 取样竞态与探针三修都由这一轮独立复核，不再是我本机结论。

**控制面 job**（`Check formal entry and browser contracts`）：V2 正式入口自检 52/52；`V2.1.2-10`（旧 Product V1 路由未被破坏）PASS；`V2.4.3-03..-13` 全 PASS，其中 **`V2.4.3-04`「正常批次：一次确认即整套提交、各提交一次并核对到」PASS**——即我改的 `wait_batch_settled()` 同次取样判据在 CI 时序下成立（本机复现不到该竞态，故以 CI 为准）；`V2.4.4-00..-10`、`V2.5.1/2/3/4/5`、`V2.6.1/2/3/4`、`UI2-*`、`V2.1.1/1.2/1.3/1.4/2.2.1/2.2.3/2.3.x/2.4.1/2.4.2` 全 PASS。

**Docker job**（真实一次性容器 + 锁依赖 Playwright Chromium）：

| 步骤 | 结果 |
|---|---|
| 5 `Build immutable image` | success（`docker build` 真跑，非静态闭包） |
| 6 `Smoke-test container health` | success |
| 8 `Release transaction selftest (real disposable containers)` | **32/32 通过，0 失败** |
| 9 `Release failure classes (real script, no containers)` | **13/13 通过，0 失败** |

自检里与验收判据直接对应的原始行：

- `ST-02-A` 旧版正式 Dockerfile 独立上下文真实构建（marker A）、`ST-02-B` 新版（marker B）、**`ST-02-IDs` 两轮真实 image ID 不同**（不用同一 image 换 tag 充数）。
- `ST-03` 隔离旧服务基线健康且实际 marker 为 A、**`ST-03-TLS` 显式信任隔离 CA 的 HTTPS 基线**。
- **`ST-DATA-01` 在真实容器 origin 上用真实 UI 建立项目并导入合法项目包**。
- `ST-04` 变异前失败保留原服务/TLS 且无开放事务；`ST-05` 真实 deploy 开放事务并保留旧容器/配置；`ST-05-stale` 过期 finalize 拒绝且保留真实恢复点；`ST-05-dirty` 脏恢复点拒绝部署且不删任一容器；`ST-06` 新版 health 绿但坏静态 finalize 判红且 previous/journal/备份保留；**`ST-07` 实际回退回到真实旧 image ID/marker A 并清除事务**；`ST-08` 成功 finalize 清除恢复点且保留健康新服务（真实新 image ID/marker B）。
- `ST-LIVE-01..08`（真实产品 origin：health 无业务状态、能力且默认付费档关闭、首页外壳、样式/`entry.js`/`app.js`、页面实际启动且无工程诊断、隔离项目新建后刷新仍在、原生下载/导入分配独立身份并刷新恢复、会话零 console/page/网络错误）、`ST-10` 页面验收对被测真实容器 origin 判绿。
- **`ST-RECOVERY-01..05` + `ST-11`**：期间确实换过真实版本（marker 由旧变新）且原项目身份/版本化文档/资产字节/人工采用记录逐条保留——**同 origin 跨版本切换与失败回退后的浏览器数据恢复**，与服务回退分开记。
- `ST-09` 与 `ST-DEAD-01..05/99`：负例基线按设计判红（`[FAIL]` 行是期望中的不可达入口结果），机制为 `net::ERR_CONNECTION_REFUSED`（`ST-DEAD-99` 原文 `Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:43807/`），**不是 `ERR_UNSAFE_PORT`**——即上一轮 ST-09 的机制修复在 Linux runner 上同样成立。

部署类步骤（10–17：SSH、远端构建部署、静态资源与页面主链验收、指纹、finalize、证据上传、回滚）在本轮**按设计 skip**：这是 PR 运行（`event=pull_request`），发布只在 main push 发生。因此本轮只证明“机制与镜像级发布事务”，**不冒充已完成线上发布**；线上发布/指纹/finalize 由合并后的 main 运行承担。

## 第四/五次CI：同一类下载超时，两次落在不同步骤（基础设施，非产品）

| run | 候选 | 失败步骤 | 原文机制 |
|---|---|---|---|
| [37760499569](https://github.com/JusticeSc/listing-kit/actions/runs/37760499569) | `8a9e3bd`（只加 docs/state） | Docker job `Build immutable image` → `uv sync --locked --no-dev` | `Failed to download distribution due to network timeout. Try increasing UV_HTTP_TIMEOUT (current value: 30s)`（`pillow==12.3.0`） |
| [37762306228](https://github.com/JusticeSc/listing-kit/actions/runs/37762306228) | `639661c`（Dockerfile 加超时） | 控制面 `Install uv and locked dependencies` → host `uv sync --locked` | `Failed to fetch: https://mirrors.tuna.tsinghua.edu.cn/…/httpcore2-2.13.1-py3-none-any.whl`、`Request failed after 3 retries`、`operation timed out` |

两次都发生在**依赖下载层**，索引是 `pyproject.toml` 里固定的清华镜像（`[[tool.uv.index]] default = true`）；同一 tree 的前一轮构建/安装通过，故不是代码回归，也不是产品行为。第一次的修法只覆盖了 Docker 构建路径，第二次证明同一类故障还会落在 runner 的 host `uv sync` 上——所以改为**按类修**：

- `.github/workflows/ci-cd.yml` 增加 workflow 级 `env: UV_HTTP_TIMEOUT=300 / UV_HTTP_RETRIES=5`（覆盖所有 job 的 `uv sync`/`uv run`）。
- `Dockerfile` 的 `ENV` 同步为 `UV_HTTP_TIMEOUT=300 / UV_HTTP_RETRIES=5`（覆盖镜像构建，包括远端服务器上的构建）。

两个变量名用 `uv` 自身解析错误实测确认存在（`Failed to parse environment variable UV_HTTP_TIMEOUT/UV_HTTP_RETRIES with invalid value`），不改索引、不改 `uv.lock`、不碰产品代码。**边界**：这是构建期下载超时，不是产品/启动间歇；不能用“连续绿”当证明，因此这里只声明“机制对应的受控放宽”，若再次出现同类失败则按基础设施问题如实报告，不靠重跑洗绿。

