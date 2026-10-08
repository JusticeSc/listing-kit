# 本机回环「同源请求 net::ERR_CONNECTION_REFUSED」机制取证与修复

NOT-AUTHORITY: 时点证据，不是目标或进度权威。目标/依赖见 `docs/product-v2-refactor-plan.md`，进度见 `_working/amz-listing-kit-product-v2/state.md`。

## 现象（用户报告，不重跑确认）

`tools/verify_v2_4_4_candidate_blob.py` 在 Windows 上多次启动失败：页面加载期偶发同源模块请求 `net::ERR_CONNECTION_REFUSED`（例：`/domain/suite-review.js`、`/storage/migrations.js`），`boot()` 未完成 → `#new-project-name` 保持 disabled，验证器在 prep 阶段超时。历史证据 `evals/product-v2/v2.4.4-candidate-blob-20261007-204328-resume5.json`。

## 机制取证（三步，全部为真实产品服务器 + 真实 Chromium/裸 socket）

| 探针 | 变量 | 结果 |
|---|---|---|
| `_working/_probe_boot_refusal.py` | 只改 accept backlog（5 / 128） | backlog=5：25 次加载中 1 次失败（峰值并发建连 8）；backlog=128：0/25 |
| `_working/_probe_backlog_mechanics.py` | 监听但不 accept，16 条并发 connect | backlog=5 与 128 均 **0 拒连** → 排除「backlog 溢出」为根因 |
| `_working/_probe_conn_reuse.py` | 裸 socket，只改「是否复用连接」 | churn 22000 次建连 0 失败；reuse 22000 次请求 0 失败 → 裸 socket 无法复现 |

关键观测（`_probe_boot_refusal2.json`）：失败请求**服务器从未收到**（`attempted_paths_seen_by_server: []`），而同一时刻端口裸连接**仍然可达**（`port_reachable_after_failure: true`，另有 `_probe_boot_refusal.py` 的同项）。即失败发生在「建立连接」这一步，不是服务器接受队列或业务处理失败。

规模测量（同一探针，各 1000 次真实页面加载）：

| 协议 | 加载次数 | 失败加载 | 服务器收到请求数 | 耗时 |
|---|---|---|---|---|
| HTTP/1.0（每请求一条连接，产品原状） | 1000 | 2（#2、#677） | 56922 | 211.2s |
| HTTP/1.1 连接复用（同一服务器、同一客户端） | 1000 | 0 | 57000 | 152.2s |

累计样本：HTTP/1.0 = 1150 次加载 3 次失败（3/114942 请求）；HTTP/1.1 = 1150 次加载 0 次失败（0/65550 请求）。服务器侧同一时期出现 `ConnectionAbortedError: [WinError 10053]`（读下一请求时对端中止）。

## 结论与残余未知

- 已定：现象是**建连期失败**（服务器未收到请求、端口仍监听）。已排除：端口 TOCTOU／重复绑定（前轮已修，且本轮用 0 号端口读回）、accept backlog 溢出（确定性实验 0 拒连）、裸连接高频 churn（22000 次 0 失败）。
- 未定（**不得声称已根治**）：Windows 回环上 Chromium 侧 `WSAECONNREFUSED` 的确切触发点未能复现为最小机制；只能证明「每请求一条连接」时命中率约 1/38000 请求，连接复用后 1150 次加载 0 命中。
- 因此修复定位为**消除触发面 + 如实报告**，不是「已证明根因」。

## 产品修复（`app/product_v2_server.py`）

1. `ProductV2Handler.protocol_version = "HTTP/1.1"`：所有响应（静态、JSON、图片字节、`send_error` 错误页）都带 `Content-Length`，因此复用连接是安全的；浏览器与生产反代（Caddy→应用）因此都按 keep-alive 使用，每页面建连从 ~57 次降到 ~6 条。
2. 未消费正文一律关连接（`_drop_connection()`）：Content-Length 不可解析、超过 `DRAIN_ABSOLUTE_MAX` 提前收手、正文没读满、未知 POST 路由、GET 带正文；响应同时补 `Connection: close`，避免客户端误以为还能复用。
3. 写响应失败（`ConnectionError/OSError`）关连接；新增 `handle()` 只吞「客户端中止」这一预期断连，不再让 Windows 10053 冒泡成 traceback。
4. `_images_result` 改走 `_send_bytes(..., extra_headers=...)`，与其它响应共用同一个带 Content-Length 与连接判定的写出点（消除重复的第二份响应拼装）。
5. 自检新增两条永久断言（`app/server.py --check`，实测条目数 45 → 47，消费者只断言「全过」，不写死条数）：同一连接连续两次请求按序返回；未知 POST 路由回 404 且关闭留有未读正文的连接。

## 验证

- `uv run --locked python app/server.py --check` → 48/48 通过（含新增两条连接复用/去同步断言）。
- 机制规模测量见上表；验证器侧结果见本轮交付证据中的 4_4 记录（保留 `boot_retries` 记录式重试：重试仍失败即判红，不掩盖产品缺陷）。
