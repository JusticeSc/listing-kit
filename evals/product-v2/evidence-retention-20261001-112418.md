# Product V2 证据保留清单 · 2026-10-01 11:24:18 +08:00

NOT-AUTHORITY: point-in-time retention and recovery record only

## 处理结果

- 扫描未跟踪文件：2,452 个；提交前去除保留报告的 2 个尾随空格后，清单总计 249,069,543 bytes。
- 留在仓库并纳入版本控制：16 个；理由仅限当前权威引用、当前完成矩阵证据及其机器可读配对、当前控制校准输出。
- 迁出仓库：2,436 个；其中旧材料引用 498 个、重复内容 283 个、未引用探索/重复输出 1,655 个。
- 未永久删除文件；全部迁出项均保留原相对路径和 SHA-256，并逐文件验证移动后的哈希。

仓库外可恢复归档：
`E:\workbuddy_workspace\2026-09-20-16-38-19\_archives\amz-listing-kit-evidence-20261001-112418`

完整逐文件清单：`manifest.json`（SHA-256
`3f88f9aa9962544a6402c24bf1320e6ca5d8a84059e3ec3232a03a1eb2e8fa36`）；便于人工查看的
`manifest.csv`（SHA-256 `11abe4a82af161884031c6ff4ec274751b8a7cc513272aa618b5b02580c556a3`）。

## 仓库内保留的 16 个文件

1. `evals/product-v2/evidence/remote-real-e2e-20261001-043317-lamp01-failure.png`
2. `evals/product-v2/remote-no-model-roundtrip-20261001-084750.txt`
3. `evals/product-v2/remote-no-model-roundtrip-20261001-084750.json`
4. `evals/product-v2/v2.1.1-indexeddb-20261001-100808.txt`
5. `evals/product-v2/v2.1.1-indexeddb-20261001-100808.json`
6. `evals/product-v2/v2.1.2-project-home-20261001-100813.txt`
7. `evals/product-v2/v2.1.2-project-home-20261001-100813.json`
8. `evals/product-v2/v2.2.1-product-contracts-20261001-100841.txt`
9. `evals/product-v2/v2.2.1-product-contracts-20261001-100841.json`
10. `evals/product-v2/v2.3.1-suite-registry-20261001-100852.txt`
11. `evals/product-v2/v2.3.1-suite-registry-20261001-100852.json`
12. `evals/product-v2/v2.3.2-suite-editor-20261001-100855.txt`
13. `evals/product-v2/v2.3.2-suite-editor-20261001-100855.json`
14. `evals/product-v2/v2.ui.1-remote-entry-20261001-104540-current-audit-final.txt`
15. `evals/product-v2/v2.ui.1-remote-entry-20261001-104540-current-audit-final.json`
16. `evals/product-v2/v2.ui.2-interaction-visual-20261001-105938control-calibration.txt`

## 恢复规则

需要追查旧证据时，先在 `manifest.csv` 按原相对路径、分类、引用来源或 SHA-256 定位；只恢复目标文件，
不得整批复制回 `evals/product-v2/`。恢复后必须重新判断它是否属于当前最小可复检集，不能因为曾被旧报告
引用就自动升级为当前证据。

BOUNDARY: 本清单证明本次文件归档、哈希校验和当前保留集合，不证明 C15/C17 或 Goal 完成。
