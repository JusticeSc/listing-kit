<!-- 拆分件 15/29 · 父文档 docs/product-v2-refactor-design.md -->
# 历史基线：最终两轮、发布与当前启动入口
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.14-historical-credentials-and-retirement.md) · [下一主题](product-v2-refactor-design.16-current-goals-and-design-assets.md)

#### 11.6.6 D：最后改动后的同候选两轮

冻结包含TS源、实际JS产物、服务/Adapter、runtime/public配置的不可变候选身份，串行运行期间不让其它代理/进程改产品。正式命令：

```text
uv run --locked python tools/verify_v2_7_1_regression.py --rounds 2 --stamp <本次唯一候选标识>
```

尖括号是实施时替换的参数，不是已执行结果。命令集合以当前`.github/workflows/ci-cd.yml`与`config/product-v2/verification.json`双守卫为准，不硬编码旧34/44计数。`--only`/单轮/局部label运行只作诊断，不作为最终准出；有red保留真实round与输出，修后受影响候选重新冻结，不能拼跨版本通过。

当前runner指纹覆盖script/args/rc/signals，不覆盖产品源字节，须另保留运行前后不可变commit/tree及source/emit/config字节身份，不能用result指纹等同“同代码”。runner已保留非零失败且继续收集后轮，并非自动洗绿。现有子验证器多用时间戳命名；不因未显式传r1/r2 label便断言覆盖。记录两轮实际原生工件路径并确认无碰撞；只有观察到碰撞才做最小修复，新增label若参与args指纹须仅规范化标识差异、不得抹平语义参数。不得为这一猜测新建回归平台。

两轮全绿、源码/产物身份一致后刷新当前适用RC/结构矩阵及历史证据范围；C17/C15注明未发生，不升为真人通过。中间阶段不提前另做两轮；若只有合并commit变化且实际源tree/字节完全一致，建立映射，不仅因HEAD不同强买第三轮。任何产品/config字节变更则重建受影响候选证据。

#### 11.6.7 E：沿现有发布事务交付

使用A前置已预检的保护与审查资格，合并/发布仍以当时实际规则及授权为准；保护不足不能直接推main、绕过或追认旧PR review。CI沿既有types/generated/domain与登记浏览器门→真实Linux Docker→健康→release selftest/offline rollback→获批Secrets/SSH→部署→HTTPS页面smoke→fingerprint→finalize→工件上传与失败恢复执行，不新增CD平台。本机Windows无Docker daemon不能用本地假绿替代Actions证明。

新候选commit/tree映射、镜像ID、runtime/public/served_scripts指纹、HTTPS同源实际页面与release.json对应后才称发布该候选成立。原机制证据有效则复用；按合同核对新候选数据/恢复材料，不无故再次生产回退。发布事务exit1沿现有受控rollback，exit4需人工处置时保存现场并精确升级，不盲回滚/删previous或用户库。Secret只走获批运行注入，不读取GitHub值/打印key/要求用户粘贴。

本节保留2026-10-08“基线先行”的历史设计来源，**不再用其将显著视觉/人因问题后置**；当前交付优先级取计划§17.13及本设计§13。精确对象、外发/费用、Unknown、普通用户负担、视觉层级和真实内容的布局都要在工程交付前按具体任务核实；C15/C17另列未发生，不代替这些工程修正。规格、局部验证、完整工程和实际发布分别判断。


## 12. 给下一轮执行模型的启动入口

以`docs/INDEX.md`§1为唯一读取路由；先判state当前门与真实Goal，再读计划§17.13及§17.2–17.5的当前包，具体问题/验收取关联Issue，只加载该包受影响的§13合同和现有owner。最新用户授权/工具阻塞优先于本文的历史准备权限；工具不可用不创建本地Goal替身，也不据旧设计启动产品。

当前实现规格取§13，费用/次数/实施批次只取原账与state。已成立的owner收口、五图原件和两包恢复按未变前提复用；新增Prompt/界面质量缺口不被旧局部green覆盖。具体Issue/PR流程与skill产物只取AGENTS，设计不另立工作流。

早期§12的五阶段、§16预算及“先再做一次套图准备”启动文本已退出日常入口，原字节可从本轮维护前快照追溯。文档/守卫通过只证明规约及恢复一致，不证明产品修复、真图品质、最终两轮、线上交付或独立真人验收。


