NOT-AUTHORITY: point-in-time V2.R2.3 research evidence; not a product implementation, release acceptance, dependency approval, or human walkthrough.

# V2.R2.3 · 问题导向成熟系统研究

输入：`ui-baseline-20261001-chrome.md` 中 B01/G01/H01/H02/H03。只读公开源码/文档；不安装上游、不运行上游模型、不复制代码/样式、不新增依赖、不上传素材。采纳结论由 context SEL-019 管辖，交互结论由 UI 合同管辖。

## 固定上游身份与许可

| 系统 | 观察固定提交/版本 | 实际许可与采用限制 |
|---|---|---|
| pi / packages/ai | `88ff80b986e34d4fbd1fa94a4df65c60ae964516`，`@earendil-works/pi-ai 0.99.2` | 根 LICENSE 与 package.json 为 MIT，Copyright (c) 2025 Mario Zechner。可学习概念；本轮不拷贝、不添加 npm 包。若未来复制/依赖需许可证随附、选型及依赖登记 |
| ComfyUI | `2d6b73283af2447bdd065ece4090b8c6b1784544`，`comfyui_version.py` = `0.38.0` | 根 LICENSE 为 GNU GPL v3 文本；本轮不判定 only/or-later，不复制任何 GPL 代码、不引入运行依赖 |
| Open WebUI | `8bd8b4fac5e059578ac0c74b3c18d11139f88b7d`，package.json = `0.11.4` | 自定义 Open WebUI License，非简单 MIT/BSD；§4 限制移除/替换品牌并规定例外。LICENSE_HISTORY 不给当前代码追溯授权。本轮只学习通用交互概念，不复制代码、样式或品牌 |

固定身份来源：[pi commit](https://api.github.com/repos/earendil-works/pi/commits/88ff80b986e34d4fbd1fa94a4df65c60ae964516)、[pi package](https://github.com/earendil-works/pi/blob/88ff80b986e34d4fbd1fa94a4df65c60ae964516/packages/ai/package.json)、[pi LICENSE](https://github.com/earendil-works/pi/blob/88ff80b986e34d4fbd1fa94a4df65c60ae964516/LICENSE)；[Comfy commit](https://api.github.com/repos/Comfy-Org/ComfyUI/commits/2d6b73283af2447bdd065ece4090b8c6b1784544)、[version](https://github.com/Comfy-Org/ComfyUI/blob/2d6b73283af2447bdd065ece4090b8c6b1784544/comfyui_version.py)、[LICENSE](https://github.com/Comfy-Org/ComfyUI/blob/2d6b73283af2447bdd065ece4090b8c6b1784544/LICENSE)；[Open WebUI commit](https://api.github.com/repos/open-webui/open-webui/commits/8bd8b4fac5e059578ac0c74b3c18d11139f88b7d)、[package](https://github.com/open-webui/open-webui/blob/8bd8b4fac5e059578ac0c74b3c18d11139f88b7d/package.json)、[LICENSE](https://github.com/open-webui/open-webui/blob/8bd8b4fac5e059578ac0c74b3c18d11139f88b7d/LICENSE)。

## 具体实现与采纳/拒绝

### 1. pi：用途、能力、协议 Adapter、凭据不是同一字段

实际读取：[types.ts](https://github.com/earendil-works/pi/blob/88ff80b986e34d4fbd1fa94a4df65c60ae964516/packages/ai/src/types.ts)、[models.ts](https://github.com/earendil-works/pi/blob/88ff80b986e34d4fbd1fa94a4df65c60ae964516/packages/ai/src/models.ts)、[auth/helpers.ts](https://github.com/earendil-works/pi/blob/88ff80b986e34d4fbd1fa94a4df65c60ae964516/packages/ai/src/auth/helpers.ts)、[openrouter-images.ts](https://github.com/earendil-works/pi/blob/88ff80b986e34d4fbd1fa94a4df65c60ae964516/packages/ai/src/api/openrouter-images.ts)。

- `Model/ImageModel` 分类型，`generateImages` 与聊天 `stream/complete` 分操作；`model.api` 决定线协议实现。图片输入/输出能力与模型名分开。
- `envApiKeyAuth.resolve` 明确先读提供的 credential key，再读列出的 env var；这不是本产品的默认 key 可送任意目标的授权。
- `KnownImageApi` 在该提交只列 `openrouter-images`；具体 Adapter 组装 image modalities、解析响应图片，不能用聊天 Adapter 数量宣称多图片协议已实现。该调用是一次性结果，不自动带来异步 task 恢复或 B01 的执行溯源。
- **采纳 G01 的概念**：用途/能力/协议/凭据分层；设置显示非秘密的有效身份、配置来源与能力，BYOK 显式覆盖时鉴权失败不静默降级到默认付费 key。
- **本地适配**：BYOK 首轮只保留于内存会话，不将 pi 的持久凭据存储移到 IndexedDB/localStorage。执行身份仅保存非秘密 credential reference 与原协议/目标/模型/请求配置。用户 endpoint 不能继承部署默认 key。
- **拒绝**：pi-ai/Node 网关/SDK 批量依赖、OAuth/动态目录、任意模型路由、隐式回退或隐藏重试；不据此选择 OpenRouter 为第二真实生图模型。仍须 R4.1/R4.2 的能力/费用/许可/批准。
- 删除/Locality：概念无移除代码成本；本地统一有效配置的 Module 集中解析/安全，删除当前多处 env/默认/覆盖的重复解析，不添加只转发的 facade。

### 2. ComfyUI：结果必须追溯当时提交快照，不读当前编辑头

实际读取：[execution.py](https://github.com/Comfy-Org/ComfyUI/blob/2d6b73283af2447bdd065ece4090b8c6b1784544/execution.py)、[server.py](https://github.com/Comfy-Org/ComfyUI/blob/2d6b73283af2447bdd065ece4090b8c6b1784544/server.py)、[nodes.py](https://github.com/Comfy-Org/ComfyUI/blob/2d6b73283af2447bdd065ece4090b8c6b1784544/nodes.py)、[comfy_execution/jobs.py](https://github.com/Comfy-Org/ComfyUI/blob/2d6b73283af2447bdd065ece4090b8c6b1784544/comfy_execution/jobs.py)。补充 [workflow metadata docs](https://docs.comfy.org/development/api-development/workflow-metadata) 为可变文档，不充当固定版本源码。

- `PromptQueue.get()` 对提交条目 deepcopy；`task_done()` 将这个当时条目放入 `history[prompt_id].prompt` 并挂 outputs/status；`get_history(prompt_id)` 按原 id 查找，缺失返回空，不重新提交。该观察范围是内存队列/历史，不能当作跨服务重启持久化证明。
- `SaveImage.save_images` 从执行输入写 `prompt` 元数据；执行图与编辑画布 workflow 是不同概念。文件内元数据不是签名、可能被重新编码去掉，不应升级为本产品权威。
- **采纳 B01 不变量**：交付 `Selection → Candidate → 原 action Attempt → frozen Prompt`；当时请求来源与当前配置/Prompt 分开。当前本地 `workspace.js:5703` 已取候选原 Attempt，却在 `5704/5714-5715` 取当前 `promptRecordOf(shot_id)` 写 manifest，正是错误来源。原 Attempt 已冻结 `prompt.version/hash`，修复应删除该当前头取数，不新建 provenance store。
- **采纳 H03 不变量**：恢复按明确 action/task 身份，Unknown 不变成 completed、不自动重提；停止新增仅停止未提交队列，不谎称取消上游。
- **拒绝**：Comfy server queue/history/用户管理/WS 为产品状态权威、图编排平台、PNG 元数据嵌入新功能、GPL 代码、未知状态落 completed 的默认分支。已有 IndexedDB 与当前格式项目包继续是持久权威。
- 删除/Locality：修 B01 使用已有原 Attempt 冻结字段，移除错误查询点；Unknown 的业务 Module 持有状态/身份规则，UI 不再自行重拼恢复路径。引入完整 Comfy 平台会增加第二状态域、备份/凭据/迁移负担，不删除本地复杂性。

### 3. Open WebUI：图像聚焦、版本导航、可操作错误；不冒充图像比较系统

实际读取：[Image.svelte](https://github.com/open-webui/open-webui/blob/8bd8b4fac5e059578ac0c74b3c18d11139f88b7d/src/lib/components/common/Image.svelte)、[ImagePreview.svelte](https://github.com/open-webui/open-webui/blob/8bd8b4fac5e059578ac0c74b3c18d11139f88b7d/src/lib/components/common/ImagePreview.svelte)、[Artifacts.svelte](https://github.com/open-webui/open-webui/blob/8bd8b4fac5e059578ac0c74b3c18d11139f88b7d/src/lib/components/chat/Artifacts.svelte)、[FileCompare.svelte](https://github.com/open-webui/open-webui/blob/8bd8b4fac5e059578ac0c74b3c18d11139f88b7d/src/lib/components/chat/FileNav/FileCompare.svelte)、[Error.svelte](https://github.com/open-webui/open-webui/blob/8bd8b4fac5e059578ac0c74b3c18d11139f88b7d/src/lib/components/chat/Messages/Error.svelte)、[Connections.svelte](https://github.com/open-webui/open-webui/blob/8bd8b4fac5e059578ac0c74b3c18d11139f88b7d/src/lib/components/chat/Settings/Connections.svelte)。

- Image 点击聚焦预览，ImagePreview 有明确关闭与 Escape；其原生实现使用外部 panzoom/通知/下载依赖和手动 body scroll lock，本地不复制这些实现。
- Artifacts 的前后版本索引有夹界/禁用；它针对 HTML/SVG artifact，而 FileCompare 是文本 diff。所检查路径**没有证明参考/旧/新图片对比、人工采用、原任务追溯能力**，不能把 text diff 宣称图像 comparator。
- **采纳 H02 概念**：同 Shot 中保持参考、旧/新候选及身份标签直接可比较；候选导航明确当前版本、不自动切到最新；比较/采用入口不置于整套长卡之后。布局需 R2.2 原型测量，不从上游概览预定三栏。
- **采纳 H03 概念**：状态/影响/下一动作常驻相邻，代码/id 放可展开详情；不复制 raw JSON stringify 错误到 UI，更不能回显秘密。重要失败不只 toast；正确保存/核对反馈再用非抢焦点状态提示。
- **采纳 G01 概念**：设置显示用途、目标、配置来源、能力/缺凭据，秘密字段遮罩且会话内保管。验证连接是显式网络动作，不把“已保存设置”当成真实能力校准或免费验证。
- **拒绝**：聊天账户/服务器保存/localStorage token、admin roles、Svelte/图像查看依赖、CSS/品牌移植、raw error payload 回显，Enter anywhere 自动确认付费/采用。使用当前稳定 Chrome 的原生 dialog/details 和既有 ESM 自写所需交互。
- 删除/Locality：一处 Shot 图片工作区拥有候选焦点/比较/返工入口，删除跨屏记忆与重复上下文；一个异常投影解释同一状态，不引入完整通知框架。概念无上游删除成本；若新增运行依赖则重开选型门。

## 自身问题到原型/验证的输入

| 本地问题 | 研究后的设计输入 | 不可放松的判据 |
|---|---|---|
| B01 | 交付来源只读采用候选原 action 快照 | 旧候选 manifest Prompt 与原 Attempt 相等，不与当前头混同；四图片字节不变 |
| H01 | 关键事实待处理队列与受影响 Shot 定位 | 必要逐项确认保留；未知事实阻断新提交，成功历史不丢 |
| H02 | 同 Shot 直接图像对照/候选前后导航 | 高频比较不依赖记忆另一屏图；图身份/版本/采用状态非仅颜色；无自动改选 |
| H03 | 已知 task 与无 task Unknown 分开，详情渐进披露 | 已知 task 核对不增加 submit；无 task 明确不可查询/重提风险；错误给影响和下一动作 |
| G01 | 非秘密配置身份与用途/能力/协议/凭据分层 | secret 不持久/不导出；默认 key 不送用户目标；历史任务不按新设置猜身份 |

## 指导工具范围与验证限制

已执行缓存的 modern-web-guidance search/retrieve（html 与 native dialog）及 UI/UX guidance 查询。两次 design-system 查询仍给营销 landing 模式，拒绝其 Hero/CTA/外部字体/配色，不把 off-topic 结果当作已验证产品设计。使用现有系统字体/视觉 tokens 与 native dialog 的焦点/Escape能力；不添加 npx runtime 依赖、不改用户日常 Chrome 设置。

本报告证明固定来源、版本、许可证与问题映射；**未运行三套上游应用，不证明其实际模型能力/稳定性，也不修复本地 B01**。本地 B01 的实际下载反例来自 R2.1，不重复“跑绿”关闭它。没有新依赖/付费/供应商/部署授权；人审及完整 RC01-RC20 仍开放。
