<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/specification-consolidation-20261004.md -->
# 4. 原字节快照与指纹
[返回 specification-consolidation-20261004.md](specification-consolidation-20261004.md)

## 4. 原字节快照与指纹

改动前原字节保存于 `_stage-amz-control/spec-consolidation-20261004/`；五份快照的完整文件SHA256与改前源文件逐项一致。以下值来自原生 `sha256sum`，不是reader输出拼接。

| 文件 | 改前SHA256 | 改后SHA256 |
|---|---|---|
| plan | `f62a7e8618c2f79170424a6a958d5040cb3e326f6dff356dc1950390d4c07c82` | `e3f60af0c88335914b3b73aa86578b587a047a2fca9d5cd1bcbf6a67a198ff19` |
| context | `8b3392eaaed0e577a6379594762406fd4df2cbfb17dac4680afca667211a9569` | `e793f0c8730b25d4db32edb0355e00636430a392c189462e04457668c133f77a` |
| UI | `4536027041793e6c86dc1b7ea3777a5f53ce69105738b5ee169efd29f8dcc1b4` | `3b47ec3c5c7355c158c2e4ad7713370d3ef09759fe98f655b0533bb2232f7411` |
| INDEX | `0c0f07668718c42d662cd221fd3f09f0d123cc8fb42cbdd8219b1ad371572d88` | `d0bd8e4de532a7da97f6f7598e60b0a7818703820da54cfdc7c64c93ab3e335e` |
| state | `9c17fd46273183d7b5708de7efc87b52e62f1c6cd866ab00a7cffeacae419707` | `1c4ae33d983be9a21bc61d2c1d61f85b4c3c3bb25bbd904e26e15cb9fd157c9f` |

## 5. 针对性验证

实际串行执行，整条命令退出码0，耗时15.71秒：

| 检查 | 实际结果 | 证明范围/限制 |
|---|---|---|
| `uv run --locked python tools/check_docs.py --no-run` | 全过；登记61/实际61，直接依赖/锁/vendor/模板映射一致 | 文档登记/静态一致性；明确未执行文档中的legacy命令，不声称这些命令本轮可运行 |
| `uv run --locked python tools/check_project_state.py` | J0–J10全过；工作记录5份 | state与计划任务/依赖/历史绑定证据结构一致；不是当前系统Goal查询或产品验收 |
| `uv run --locked python tools/refactor_resume.py` | PASS；8阶段/26任务；唯一next=`V2.R6.3`，明确blocked且只准解除三项输入/权限门 | 实际冷恢复入口读取本轮任务卡，未回到旧发布或R1.1，不执行受限产品动作 |
| 冷恢复输出Goal原文SHA256 | `3f9f1842d67d063fa9d8cfbbaf60eb5971fe24b46502c97455241ccac40d4607` | 与原指纹一致；未改变§2.1原文。输出仓库历史active/required观察，同时明确脚本不查询系统Goal；本轮实时No active goal不能被该历史读数覆盖 |

无产品代码/配置改变，不新增测试、验证器或运行产品回归，不重复既有64向状态探针；阶段/任务状态及依赖未变。规约层交付成立，产品落地/可点击原型/真实图文请求/图片质量与人审均未验证，不据此称工程完成、可发布或Goal完成。

## 6. 施工批次与必要验证追加（同日后续用户指令）

用户要求详细实施规划，明确担忧重复验证成本、不得以测试/报告替代实际开发。已在原计划§15给出六批顺序：设置真实接线→人工事实/用途→默认生成→比较/返工/交付→真正图文辅助→最终集成。每批列明具体动作、消费者位置、可操作完成点及最小证明；仅为规划，不创建新任务/第二进度表，不施工。

计划§7.3/§15.3规定：不逐编辑运行；完成连贯批次后按影响选最小检查并实际smoke；复用未受影响证据；扩大检查须说明传播风险；不新增接线/命名/文案/mock回声测试、探针或报告平台；失败定位/修复后才重验。既定R7.1最终两轮离线回归保留到最终，不逐批执行；真实调用不随回归重复，付费门/秘密/OCC/Unknown/字节来源保护不取消。AGENTS提交前状态/依赖变更反向探针仍遵守，不误解为每次编辑/进度更新都运行。

本次原字节快照：`_stage-amz-control/implementation-batches-20261004/`，包含改前plan/state/本证据。§4–5为首次规约合并的时间点，以下是本次追加后的最新权威文件指纹：

| 文件 | 本次改前SHA256 | 本次改后SHA256 |
|---|---|---|
| plan | `e3f60af0c88335914b3b73aa86578b587a047a2fca9d5cd1bcbf6a67a198ff19` | `68b26a72473d3287e848137341b4a24ab6e3a0efdf86e80fbb698de1cf82e8da` |
| state | `1c4ae33d983be9a21bc61d2c1d61f85b4c3c3bb25bbd904e26e15cb9fd157c9f` | `036e73bdaaf3866e75ddd55ca990dd2fa1f98620dab44d808d9ef0eabc19b180` |

实际只执行一次 `uv run --locked python tools/refactor_resume.py`（随后原生sha256sum），整条命令退出码0、耗时10.08秒。源码packet内部已有文档登记/state核对，本次未再串联运行重复的独立登记/状态检查，未跑64向探针、产品回归或付费请求。输出仍8阶段/26任务、next=blocked R6.3，任务卡已指向§15；原Goal正文hash仍 `3f9f1842d67d063fa9d8cfbbaf60eb5971fe24b46502c97455241ccac40d4607`。任务/阶段状态和依赖未变，未提交。

该输出仅证明规划/恢复结构一致，不证明六批功能已经实现。本次没有重新查询系统Goal或创建/绑定Goal；历史active观察不是新施工许可，获准施工前仍需真实核对。

