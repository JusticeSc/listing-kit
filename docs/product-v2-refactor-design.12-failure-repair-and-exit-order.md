<!-- 拆分件 12/29 · 父文档 docs/product-v2-refactor-design.md -->
# 差量失败修复、运行顺序与升级门
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.11-handoff-and-delta-ownership.md) · [下一主题](product-v2-refactor-design.13-historical-baseline-startup-and-compare.md)

#### 11.5.3 失败路径与无效证明的精确修复单位

| 单位／承接 | 精确落点 | 固定前置、失败后置与修复后准出 |
|---|---|---|
| 启动拒绝／R5.1、RC19 | `verify_v2_4_4_candidate_blob.py`启动门、既有shared server与受影响正式启动层 | 保留同源URL、server真实绑定地址、进程/线程存活、request/accept/finish时点及Chrome network失败层；只有对应因果证据才能关闭。bind-0已经使用，不再归结旧TOCTOU；第二次load成功、加timeout或“环境瞬态”不是根治证据，boot_retries必须显露 |
| 候选check06／R5.1 | generation候选/批次状态、`ui/generation-view.ts`投影、同4_4原入口 | 受控result持续失败直至显式解除，观察当前失败提示、asset/candidate零半份、原attempt不丢；状态用实际flight/batch/保存后置，不匹配“批次进行中”文案。稳定可操作后明确重取，hash正确且submit计数不增加；解除前不能自动成功掩盖失败 |
| 默认摘要／R5.3 | gen/Prompt领域规则、generation-view及 `verify_v2_3_5_pre_generation_confirm.py` | 自动准备系统Prompt，不覆盖人工；独立固定输入算目标发送集合/文本/hash，UI见到值、确认记录、每shot新action及捕获请求相符。已成功4图不能再伪造4张待发，0张按钮禁用；确有新图/明确返工才验证后续授权。stale零新submit、刷新精确历史、无关图不失效 |
| 下一待处理／R6.2、R7.1 | compare领域判据、compare-view、`verify_v2_5_3_compare_panel.py`-15 | 夹具明确shot顺序、当前位置、待处理/风险类别；事先写出唯一预期及全处理边界，实际点击/焦点落点符合。不得从按钮dataset或同一被测函数求expected，不重新钉“永远第一图” |
| 真BYOK与缺key／R4.3、R6.1–3 | `verify_v2_packet08_settings_vision.py`及当前settings/三用途正式消费 | 页面实际输入可识别测试key并触发合法文字/图文/生图/显式单图和整套复核；批准上游确收指定用途/原任务身份/key，合法出站头含key不算泄漏。清输入后全DOM投影、完整响应/IDB/localStorage、实际两包、console/日志/诊断无秘密，不截固定前缀。缺key场景提供合法图片base64/hash，观察凭据分类、零上游；不能用缺图片错误证明缺凭据 |
| 旧格式包拒绝／R6.3 | 同settings原入口、transfer/import | 由真实当前导出包构造声明不支持的旧schema包、实际上传导入；预期明确拒绝且已有项目/文档/资产不变、无新项目半份。只测当前拒绝政策，不恢复旧格式兼容；删常量 `"probe-ok"`和假hash成功 |
| 发布条件／R7.4 | `.github/workflows/ci-cd.yml`及原release probe | 删除/替换扫描自己token的truth-table源码钉；由现有事务故障场景验证deploy/acceptance/fingerprint失败回退、finalize exit1可恢复回退、身份/清理exit4进入manual而非盲回退。只改真实受影响门与既有probe，不新增发布平台 |
| 容器页面／R7.4 | `release_transaction_probe.py --selftest`现有ST-LIVE与Docker/CI | 不同image ID/marker证据保留；页面对被测实际容器origin执行启动→新建→保存→刷新/重开、资源/console/network/IDB。另起fake server只能证明助手，不能署名容器产品；可信HTTPS和同origin数据恢复再由实际发布/回退轨迹证明 |

每个单位改动与旧路径删除绑成一包；能按固定前置/后置修原入口就不新增永久脚本。产品问题与验证问题分别判断：用例空证不等于产品有bug，用例红也不能直接通过改期望放行。失败现象与机制对应不足，原发布条件仍未证，不让模型自行定性为基础设施噪声。

#### 11.5.4 具体运行与最终顺序（仅恢复施工后）

下列命令均从仓库根执行，**本轮规划不执行**。源码/调用方连贯改动完成后再编译、跑最小受影响消费者；不是每项编辑后刷一遍此清单。

```text
# 改过TS的同包闭合：build包含strict检查，随后只读产物比较
npm run build:frontend
npm run build:frontend-node
# 未改TS但改变受检查调用方时用 npm run check:types；不重复同包相同诊断

# 对应差量修复后选其入口串行单跑，不为确认已有失败重跑
uv run --locked python tools/verify_v2_4_4_candidate_blob.py --label convergence-blob
uv run --locked python tools/verify_v2_3_5_pre_generation_confirm.py --label convergence-confirm
uv run --locked python tools/verify_v2_5_3_compare_panel.py --label convergence-compare
uv run --locked python tools/verify_v2_packet08_settings_vision.py --label convergence-settings
# 改报告owner/订阅时仅加实际受影响报告/采用/交付消费者
uv run --locked python tools/verify_v2_packet08_adoption_ai.py --label convergence-adoption
uv run --locked python tools/verify_v2_packet08_delivery_ai.py --label convergence-delivery

# 发布机制只在获批Linux/Docker环境：缺前提即明确阻断，不本机假绿替代
uv run --locked python tools/release_transaction_probe.py --selftest
# 对批准的部署/恢复可信origin，不带key、不收费；不忽略TLS信任
uv run --locked python tools/release_transaction_probe.py --page-smoke --base https://47.115.172.233:8080
uv run --locked python tools/release_transaction_probe.py --fingerprint --runtime-root .
```

**联调不是另造E2E平台。**用现有正式Chrome无头宿主从空项目页面上传合规参考图／填商品资料→人工事实确认→用途/尺寸补项→摘要生成→partial比较→目标返工→保留/改选→未AI交付实际下载→完整项目ZIP下载/导入/刷新。对同一项目记录页面动作、实际请求及action、IDB版本、ZIP对象/Blob/hash、焦点和真实视觉后置；不以直接种候选或调用内部函数替路径。辅助任务在同一路径上显式图文提议→人工确认，其他规则不另建；三用途配置、刷新丢key/补原key/旧task仅核对、0新submit、精确失效和真实Unknown仍覆盖。

联调同时收口§11.5.2接缝与原反例（两tab预占、late A不掩盖B、采用OCC、单快照/交付围栏、旧实例隔离），按实际改动风险复用§11.3入口，不再为owner迁移复制状态机夹具。视口1440/1366、实际浏览器125%/200%、390px关键可达及纯键盘按原UI入口实际证明；deviceScaleFactor、CSS transform或缩窗口不算浏览器缩放，截图size非零不算视觉验收。

最后一次产品/消费者修改闭合后才冻结候选：R7.1两轮按 `evals/product-v2/refactor/packet11-regression-rounds-20261007T101243Z.md`§1的34项离线清单与**当前registry/CI交集核对**，沿既有命令逐项串行，不因数字34固定新增无关检查。命令采用 `uv run --locked python tools/<该清单验证器>.py --label convergence-<验证器短名>-r1`及-r2；短名按清单实际文件唯一取值，packet08三个label绝不相同。两轮每项实际退出0、必要行为判据均成立；SKIP只证明相应离线部分，真实能力/外部门不能计为通过。原失败文件不覆盖，任一必要红都阻断冻结。

真实能力先按计划§15.6资产规则映射已有证据，不能默认购买一次理解加一次复核。RC候选/结构六项成立后，现有PR→Linux verify→正式Docker build/smoke/selftest→审查/保护→main部署→受信HTTPS/静态资源/隔离页面→完整runtime指纹→finalize依序；服务回退同image/marker和同可信origin包/Blob/历史恢复分开证。线上实际发布行只在事实发生后置proven，不能先写矩阵完成再部署。

#### 11.5.5 升级门和后续维护边界

本轮完成就是原工程Goal与结构准出共同完成，不承诺之后再补一轮总体设计。今后普通变更定位到唯一owner：商品输入/用途到inputs+既有domain，文本准备到prompts，提交/原身份到generation，单图报告/采用到adoption，交付政策到delivery，协议/凭据到现有Adapter/settings，布局到现有view；跨owner只改真实消费者，不重建系统。

新增架构/schema/权限/预算/保护规则、无法建立间歇现象—机制对应或旧证据确实失效且无许可补证，停止对应动作并精确升级；不偷偷豁免或降为“离线MVP”。用户停工则只保存恢复材料，不借“有Goal”继续。规划的3轮上限仅约束本次文档修订，不冒充恢复施工的无限重试许可，也不消耗模型调用额度。

