NOT-AUTHORITY: point-in-time continuation evidence. Not a second plan, execution-state authority, historical incident RCA, or Product V2 completion claim.

# 离线推进：存储实测、首页读取恢复与剩余准入门

## 1. 当前结论

- 保留 Phase 0–3 已完成记录与 Phase 4 active；不重做 Goal 绑定，不把局部回归当作最终验收。
- R6.4 正式路径与原始测量已补齐，发现最新版索引收益；批准/正式应用/应用后验证尚缺，R6.4 仍 pending。
- 首页原生读取失败的静默窗口已可控复现并修复。历史启动间歇问题和旧正式入口重开失败的实际触发原因仍 Unknown，不因本轮通过样本闭合 RC19。
- R4.2 仍 blocked：公开文档补证不等于模型/地区/账号/条款/素材/凭据/预算授权。
- 0 次真实模型调用、0 次私有素材上传；未提交/推送、部署、引入依赖或删除 V1。

## 2. 存储证据与索引决策

详见 [storage-contract-review-20261003.md](storage-contract-review-20261003.md) 与
[storage-measurements-20261003.json](storage-measurements-20261003.json)。

- 正式 UI 打开、资料保存与产品完整包导出函数分别实测；压力打开 154.1/154.2 ms、导出 220.3 ms。
- 长历史打开 trace 读 2582 条/6913838 B payload；独立单次导出 17 个 CDP 样本，观察最大堆 15312340 B、backing 45603362 B。两项不相加，采样最大值不是精确峰值/RSS。
- 单文档 2003 版查询的隔离原生数值索引 PoC：53.3–60.1 ms/2003 条 → 0.3–1.2 ms/1 条，五次最新版记录相等。不是生产改造收益。
- 同版本压力包文档/资产往返一致；OCC 旧版本拒绝、资产去重与哈希篡改的原子拒绝已实测。原先随意翻转 ZIP 字节的包被接受，不算损坏拒绝通过。
- 压力副本完整字节已保存在 `packages/r64-long-history-pressure-20261003.zip`（22405248 B，SHA256 `86d13d4aabea512af815179164aefbb9218244376f84d1f46f078b7ece978300`）；独立 Python 核对 CRC、全部资产 hash 和 1–2000 完整版本链通过，后续比较不依赖临时浏览器 profile。
- 原始 hash 采集曾使用默认 `read :raw` 返回值；长文件仍带 300 行截断/页脚，不能当完整文件 SHA256。原始记录已保留旧 reader-output digest 并替换为完整物理字节 SHA256。测量前 app 源码由本轮 edit 的逆变换恢复，重现原内容 tag `4A02`；不能声称编辑前就保存了完整字节快照。
- 建议批准后仅改最新版/OCC 取头查询，不改 listAll/listVersions 的完整历史语义、不引入 latest 双写表；记录格式/数据保留仍服从计划 §2.3，无兼容 shim。

## 3. 首页故障：复现、修复与边界

### 复现与因果链

[home-read-failure-before-20261003.json](home-read-failure-before-20261003.json)：
在真实项目库中让一次原生 projects.getAll 抛出 UnknownError，返回首页后行数 0、空库提示隐藏、错误隐藏、没有重试入口，并产生未处理拒绝。
旧路径 `showHome → void refresh → await projects.list → renderList` 没有读取失败投影；恢复项目时 boot 也未等待首页列表，导致初始 DOM 一直为空。
这证明静默窗口可达，不证明旧失败日志是哪一个触发分支。

### 已应用范围

- `app/product_v2/app.js`：boot 等待必需的列表读取再解锁；首页读取有 busy/loading/error/retry 投影。
- 保留上一次成功列表；先构造新行再整体替换，失败不清空、不假称空库；较旧读取结果不覆盖较新请求。
- 首页读取失败由就地重试恢复；启动必需读取失败保持控件禁用，由原启动重试恢复。
- `app/product_v2/index.html`：只增加对应状态、错误和键盘可用的重试入口；没有 schema、持久化或协议修改。
- `tools/verify_v2_3_3_session_lifecycle.py`：重开检查补上首页与实际草稿，并覆盖原生失败、键盘重试、无写入的真实 IDB 锁等待、启动列表失败。关闭测试服务器前先 shutdown；首轮完成时出现的 daemon teardown 异常头不当作产品故障，顺序修正后的新轮次无该输出。
- `tools/verify_v2_1_4_formal_entry.py`：保留原项目数/name 判据；失败会落盘准确阶段、projects.getAll 时间线、UI/pointer、独立连接 DB 快照、源码物理 hash 和截图，再重新抛出失败，不靠放宽超时或重跑。

### 已运行证据

| 检查 | 实际结果 | 原始证据 |
|---|---|---|
| 修后可控读取/原生锁/启动失败与重试 | 4 条原有项目保留；读取错误可见，Enter 重试恢复；慢读取 busy 可见；启动失败禁用，重试完整就绪 | `home-read-recovery-20261003.json` |
| 390px 实际页面 | innerWidth 390、scrollWidth 375；错误与重试可达，Enter 后仍 4 条项目 | `home-read-error-390-20261003.png` |
| 生命周期回归 | 15/15；零浏览器 console/page error | `../v2.3.3-session-lifecycle-20261003-025221-home-read-recovery-shutdown.json` |
| 正式入口/重开/服务器重启/隔离/磁盘 | 13/13；零受管磁盘差异 | `../v2.1.4-formal-entry-20261003-024816-home-read-recovery.json` |
| 项目首页 CRUD/复制资产/恢复/390px/隔离 | 11/11 | `../v2.1.2-project-home-20261003-024837-home-read-recovery.json` |
| 开发检查/直接领域行为 | 版本检查、既有 jsconfig 作用域 tsc 零诊断；223/223，不是全 app strict 类型审计 | `home-read-frontend-checks-20261003.txt` |
| 控制面与恢复路由 | 文档/状态守卫通过；15 向文档、62 向状态反向探针符合预期且字节还原；冷恢复 active、唯一下一动作 R6.4 | `home-read-control-checks-20261003.json`（观察摘要；完整后台 stdout 未形成可恢复工件） |
| 正式入口失败捕获本身 | 受控“重开回首页后 reload”触发准确阶段；UI 回工作台，但独立 DB 仍为 1 项目/1 文档/1 资产；捕获后异常不被吞掉 | `home-diagnostic-smoke-20261003.json` 与其引用的 failure JSON/PNG |

最后一行是验证器的预期失败路径 smoke，不是一次新的自然产品回归失败，也不是历史故障根因。
本轮没有验证新的 125%/200% 实际浏览器 zoom，也没有执行最终真实模型主链、C17/C15 或发布门。
修后完整物理字节 hash 与逐场景原始结果在 `home-read-recovery-20261003.json`。

### 回退材料

`_stage-amz-control/home-read-recovery-20261003/before-reconstructed/app/product_v2/` 保存本轮 UI 逆变换后的 app.js/index.html，重现编辑前内容 tag `4A02`/`1AD5`。这是编辑后恢复的回退材料，不是编辑前快照完成证据。只回退本轮 UI；测试新增覆盖仍用于揭示原静默缺陷，不降格验收。当前格式代表历史包仍在 `packages/r12-baseline-project-b-history-60docs.zip`；本轮不改用户浏览器数据或项目格式。

## 4. 第二模型公开资料补证：不替代授权

完整独立预检原文：[model-preflight-20261003.txt](model-preflight-20261003.txt)。

- [BytePlus 官方共用教程](https://docs.byteplus.com/en/docs/modelark/seedream-5-0-pro)与[价格表](https://docs.byteplus.com/en/docs/modelark/model-pricing)正文补证海外 `dola-seedream-5-0-flash-260915`，单/多图参考、PNG/b64 输出，报价 $0.018/输出图、输入免费；不是实测成本/质量/账号可用性。
- 大陆 `doubao-seedream-5-0-flash-260915` 目前有[官方模型列表的搜索索引片段](https://www.volcengine.com/docs/ark/model-list)旁证，正文/控制台、计费币种与公式仍待核实；不把海外 `dola` 前缀/价格直接套到大陆 `doubao`。
- 两边地区/目标/条款不能混用；[区域说明](https://docs.byteplus.com/en/docs/ModelArk/region-availability)未给 Seedream 的 EU 模型可用性证据。
- [BytePlus 数据处理说明](https://docs.byteplus.com/en/docs/ModelArk/BytePlus_ModelArk_Data_Processing)涉及安全过滤触发内容在 Malaysia 保留 180 天；训练用途与通用输出权属仍缺充分证据，不据此上传私有商品图。
- 同步结果无可核对 task-id；超时/5xx 后应保留 Unknown 并停止自动重提，不能伪造任务号。flash 的优化开关、参考保真、水印关闭、实际尺寸/参数支持要由获批 PoC 证明。
- 需要用户决定模型/地区和授权包：账号可用性、认可的数据条款、具体调用数/金额上限/停止规则、素材 hash 与许可、隔离进程环境变量凭据通道。密钥不要进入聊天/仓库/证据。

## 5. 精确剩余动作

执行状态只看 `_working/amz-listing-kit-product-v2/state.md`：下一任务仍 R6.4，先取得已实测索引改造的决定，不重做本轮测量。R4.2 保留外部 PoC 阻塞；其后按 R4→R5→R6 的已有前置推进。RC16 当前 Prompt 错误溯源、RC19 历史触发未知、C17/C15、V1 专批及删后回归仍未闭合。没有把这些后置任务标成完成。
