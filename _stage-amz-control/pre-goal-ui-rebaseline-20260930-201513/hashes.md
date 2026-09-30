# 正式 Goal 前 UI 重基线控制面快照

快照目录：`_stage-amz-control/pre-goal-ui-rebaseline-20260930-201513/`。

本批目的：在不启动系统 Goal、不修改产品代码的前提下，把远程 HTTP/WebCrypto 缺陷、支持浏览器边界、前端交互与视觉重构任务、Goal 验收增补和唯一下一动作纳入控制面。

| 文件 | 准备前 sha256 | 准备后 sha256 | 变化 |
|---|---|---|---|
| `README.md` | `ce32c184ced364623c05038265a15bc6fabaace6d5757832199f417b8eb2a31f` | `2709a5804fc28dceb1a783119b2fb484a95d04406a6ad30d1caf334b2e71fc31` | 改：记录远程 HTTP 缺 WebCrypto及旧错误文案边界，不冒充 V2.UI.1 已修复 |
| `AGENTS.md` | `9b98a3d4d7c6d1afbad4ca264a9d4f49d1ab1ab16974010327a6b3f57b3fb738` | `9b98a3d4d7c6d1afbad4ca264a9d4f49d1ab1ab16974010327a6b3f57b3fb738` | 未改 |
| `docs/INDEX.md` | `bc3606bfbddaaf6142bd20b81b77553144a1a89da41d9293dc66f1c65905d803` | `3bdeadf1315f5f6465f9fb6c3d1e4317bbeffb2a8d41cfc47c1e7a17b4631781` | 清理控制状态行的尾随空格；权威关系未改 |
| `docs/product-v2-goal-and-implementation-plan.md` | `68ec3a4f804073d0e544616eb530ba2615e69b5a280f7274a8c2f919cd18aecf` | `94112c1e88793574fc85732ca5139abeeeb24f5d5204522603a13793d9d89dc2` | 改：v3.1、Goal 增补、V2.UI.1–3、G5/C16/C17、依赖重排 |
| `docs/product-v2-project-context.md` | `e9a2ee17eb9c38a3482a7b6819187814bedb399046f31ec5e31904b84e40694b` | `7d716179fae9031f900e7b470e0f1922ffd467cf13edc357a060f159422556d0` | 改：SEL-012、HTTPS/browser/视觉边界与质量门 |
| `_working/amz-listing-kit-product-v2/state.md` | `21aecf2ecce28ea7a958001f5c3f536b8296cb44d9595d2dc2e38d67738937d0` | `d04f41f8999fe7d70f20348f8e7644a75ea6c2ef92882f98205b887ca78c9b40` | 改：Goal paused 读数、latest audit、next action=V2.UI.1、HTTPS 未知项 |
| `_working/amz-listing-kit-product-v2/tasks/v255-server.md` | `da42a99ba68e34279501c347d7bb46b69a164376d6a1081e6497e3bbb354b79c` | `da42a99ba68e34279501c347d7bb46b69a164376d6a1081e6497e3bbb354b79c` | 未改；V2.5.5 任务书后移但契约不变 |
| `_working/amz-listing-kit-product-v2/tasks/v255-verifier.md` | `3a5af5fa9061fc46c1c97e074d1ae9e3f3fb9d0f68d951d12111f27269eaa27f` | `3a5af5fa9061fc46c1c97e074d1ae9e3f3fb9d0f68d951d12111f27269eaa27f` | 未改 |

时点审计：`evals/product-v2/pre-goal-ui-rebaseline-20260930.txt`。快照与审计只是恢复证据；目标、架构和状态仍分别以计划、项目上下文和 state 为唯一权威。
