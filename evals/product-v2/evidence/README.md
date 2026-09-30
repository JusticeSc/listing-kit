# 入库视觉证据（final visual evidence）

本目录存放**被控制面引用、必须随仓库分发**的终版截图证据。

- 为什么入库：`_working/amz-listing-kit-product-v2/state.md` 的证据路径由 CI 守卫（J5/J6）检查必须可解析；
  浏览器截图是「界面当时长什么样」的唯一原始证据，纯文本无法替代。
- 与 `evals/product-v2/*.png` 的区别：那边是本地工作产物（每跑一次验证器就多一张，被 `.gitignore` 排除）；
  本目录只收终版——`-final` 批次或最终通过验收的那一张。
- 入库流程：验证器产出终版证据 → 控制面 `state.md` 引用改为本目录路径 → 复制文件 → 随该任务提交。
- 命名沿用验证器输出原名（`<任务>-<YYYYMMDD-HHMMSS>.png`），不改名，保持与同批 `.txt` / `.json` 可互证。
