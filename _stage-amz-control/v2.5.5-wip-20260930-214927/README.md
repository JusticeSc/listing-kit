# V2.5.5 浏览器侧未提交实现存档（V2.UI.2 开工前置）

存档时间：2026-09-30 21:49（Asia/Shanghai）。动作来源：V2.UI.2 任务书「开工前置」。
目的：把工作树里 V2.5.5 的未提交实现原样留档，保证 V2.UI.2 可以安全重构正式入口，
后续 V2.5.5 施工（依赖 V2.UI.3）可从这里取回。

## 内容

- `app/product_v2/domain/suite-review.js`：V2.5.5 冻结的浏览器侧领域契约（未跟踪新文件）。
- `app/product_v2/domain/{index,review,shared}.js`：注册整套规则与导出（工作树改动）。
- `app/product_v2/{index.html,styles.css,workspace.js}`：整套一致性卡片与工作台接线（工作树改动）。
- `wip-ui.patch`：上面三个前端文件的 `git diff`（相对当时 HEAD=adf21dc）。
- `wip-domain.patch`：三个 domain 文件的 `git diff`。

## 文件哈希（sha256，存档时）

| 文件 | sha256 |
|---|---|
| app/product_v2/domain/suite-review.js | 8a40c762867569ef386d3de935dfee911799670ab54ca78d3dad8a0f1b1c56da |
| app/product_v2/domain/index.js | 815f0f72cb711407d12a438ef212492dd613de41332a49f21e84ea27a574f589 |
| app/product_v2/domain/review.js | 569101b85018b260b170d2184b49d2cb95035028ad949f56adcb744344552c72 |
| app/product_v2/domain/shared.js | f686af5f83d2d8cddc246fc3cff3421aa3c9b22591838c2c9b2431a61227d55d |
| app/product_v2/index.html | b0870f97255e5db904006d6385651507203a75245e057861a059cf7d464f313a |
| app/product_v2/styles.css | bdb36fbddbdde14d337849b6e5662530e6951c6bc004c9b3ee8385b753ac5d92 |
| app/product_v2/workspace.js | a6f5f848b35677255797ddaf869e274d6c2cc9cf5097ed94e74bd4f9c0694edb |
| wip-ui.patch | 2e9a847fc41915612be95bfc84513895ecce075034d0fcd41a3ee79a613eae99 |
| wip-domain.patch | b25bc969482ec2538302d13e4454ad55bd387097b4e7d805c33681fb94812baf |

补记（2026-09-30 晚）：初版 patch 由 PowerShell 管道写出，行尾是 CRLF，`git apply` 会报
“patch does not apply”。已用 `git diff --output=...` 重新生成 LF 版本并覆盖；上表哈希为修正后的值。
验证：`git apply -R --check wip-ui.patch` 与 `git apply -R --check wip-domain.patch` 均通过。

## 恢复方式

在干净工作树（或指定提交）上：`git apply _stage-amz-control/v2.5.5-wip-20260930-214927/wip-domain.patch`
与 `wip-ui.patch`；`suite-review.js` 直接复制回 `app/product_v2/domain/`。
V2.5.5 真正开工时应以 `_working/amz-listing-kit-product-v2/tasks/v255-*.md` 为准重放，
不要跳过 V2.UI.3 直接把旧界面接回。

说明：本目录是快照产物，不参与 docs/INDEX 登记，也不发布当前状态；执行状态只由
`_working/amz-listing-kit-product-v2/state.md` 承担。
