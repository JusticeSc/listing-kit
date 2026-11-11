<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/reference-review-20261001.md -->
# V2.R2.3 · 问题导向成熟系统研究
[返回 reference-review-20261001.md](reference-review-20261001.md)

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

