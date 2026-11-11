<!-- 拆分件：身份、来源、运行与所有权 -->
> [product-v2-project-context.md](product-v2-project-context.md) · CONTROL-STATUS: current · AUTHORITY: project-context
> 原文第 8–77 行 · [后片](product-v2-project-context.technology-selection-000-009.md)

## 1. 项目身份

- **项目名称**：amz-listing-kit Product V2
- **目标使用者**：需要为电商商品制作一套可交付图片、但不希望从零学习复杂提示词工程的运营人员。
- **核心任务**：从商品参考图与少量商品资料出发，确认商品事实，编辑套图方案，调用图片模型生成候选，处理自动发现的问题，局部返工，人工选定并导出套图。
- **产品价值**：降低复杂生图任务的使用门槛，同时让设计者能查看和修改事实、套图、单图规格、Prompt、校验与候选关系。
- **当前平台边界**：Amazon US 通用图片要求；品类知识通过可扩展规则与动态槽位逐步增加，不假装已经覆盖全部品类。

## 2. 迁移基线与事实来源

| 层 | 稳定边界 | 事实从哪里读 |
|---|---|---|
| Product V1 | 旧文件夹工作空间与专属执行链已在本次候选中清退；保留Git历史、用户原件与选中恢复材料，不提供旧入口或旧格式迁移服务 | 当前实现取README/代码；候选验证与main/发布身份分别取state和关联PR，不以本地删除冒充线上已切换 |
| Product V2 | 浏览器拥有用户项目，Python 服务无业务状态；所有新能力都必须在这一所有权边界内实现 | 已落地行为只看 `README.md` 与代码；当前进度和证据只看 Product V2 state；目标只看 Product V2 计划 |
| 参考模板 | `docs/standards-template/` 是外部课程模板的原样副本，不是本项目运行规范 | 采纳映射、未采纳项与复访条件只在 `AGENTS.md` §Standards Mapping |

旧 Product V1 的“完成”只证明旧架构下的能力，不证明 Product V2 已经完成；未提交文件和选型 PoC
也只算候选或证据。任何“已实现”声明都必须由 README 指向的代码与范围匹配的验证证据支持。

## 3. 运行边界与数据所有权

```text
现代桌面浏览器
├─ localStorage：当前项目 ID、少量界面偏好
├─ IndexedDB：项目记录、参考图、候选图、任务身份、校验、选择和历史版本
├─ domain/：事实、套图、规格与 Prompt 编译的唯一权威（V2.3.4 起在浏览器侧执行）
└─ ZIP：完整项目包或最终交付包
        │
        │ 同源 HTTP；每次请求携带完成本动作所需上下文
        ▼
Python 无状态 AI 服务
├─ DeepSeek文字商品分析（明确未看图）／qwen-vl-max商品图文提议
├─ qwen-image-3.0 异步链 / 火山 doubao-seedream 同步生图
└─ qwen-vl-max 显式单图/整套复核（独立于商品提议合同）
        │
        ▼
外部模型 Provider
```

### 3.1 权威状态

- **用户项目权威**：浏览器 IndexedDB。
- **当前项目指针**：同一浏览器 origin 下的 localStorage。
- **外部生成执行权威**：Provider的受理/结果；异步使用真实task ID，同步以原请求/action身份及结果字节追溯。浏览器保存冻结身份与观察历史，不为同步协议伪造task。
- **服务器**：不保存工作空间、最近项目、商品图、候选图、选择或导出包。
- **项目迁移与备份**：用户主动导出的完整项目 ZIP。
- **最终采用权**：人工 Selection；模型提议和 VLM 报告都不是最终采用。

### 3.2 无状态的准确边界

无状态指“不保存用户业务状态”，不是“进程没有配置或日志”。服务器可以读取模型配置、规则版本和环境变量，也可以输出不含项目内容的运行日志。图片只在当前请求中转，不作为服务器项目文件落盘。

如果生成提交超时且浏览器没有取得 provider task ID，结果保持 `UNKNOWN`，不得自动重提。只有已知 task ID 才能由任意重启后的服务器继续核对。

### 3.3 运行与部署取值

| 占位符 | 本项目取值 | 说明 |
|---|---|---|
| 入口 | `python app/server.py` | 唯一 Product V2 无状态入口；旧`--legacy-v1`/离线fixture参数已退出 |
| 端口 | `8780`（默认） | 可用启动参数覆盖；内网穿透与否由使用者自行控制 |
| 健康检查 | `GET /api/health` | 返回 `product=v2`、`server_state=none` |
| 宿主 | 本机 Python 开发入口；远程服务器 Docker 正式运行 | 默认 Python 启动仍绑定回环地址；远程容器固定监听 `0.0.0.0:8780`，暴露范围由服务器和使用者控制 |
| 部署方式 | GitHub Actions → SSH → 远程 Docker | PR/push 先跑 CI；只有 `main` push 才传最小构建上下文，由远程 Docker 构建 SHA 镜像并替换同名容器 |
  | 容器 | `amz-listing-kit:<git-sha>` | 镜像只含V2正式入口；发布事务（`deploy/release-transaction.sh`）把 previous 应用容器与 Caddy 配置备份保留到 deploy 内验收（容器健康、受信 HTTPS、静态首页/样式/脚本）与事务外 acceptance（约定页面主链）及 finalize 重验全部结束才清理；脏恢复点（serving 与 previous 并存且无开放事务）直接拒绝 deploy；任一必要失败回退并核对实际可用性，回退失败 exit 3，收尾失败 exit 4 需人工清理 |
| 密钥来源 | 环境默认档及理解/生图/复核三用途请求级BYOK | 有限Provider选择与请求头已接入正式装配；key只在当前标签页/请求内存。实现接线不等于全用途秘密隔离验收成立，设置空证的剩余门见state及详细设计§11.5 |

浏览器支持与 origin 取值由 SEL-012 固定：本机开发可用 `http://127.0.0.1` / `localhost`；远程正式入口必须经可信 HTTPS 暴露。固定端口 `8780` 是容器内部/服务器监听端口，不等于要求用户直接访问明文 `http://<IP>:8780`。

2026-09-30 落地（V2.UI.1）：TLS 终止在 Caddy 容器（配置 `deploy/caddy/Caddyfile`，由 `.github/workflows/ci-cd.yml` 的部署步骤收敛），使用 Let's Encrypt IP 证书 shortlived profile 自动续期，HTTPS 对外监听 8080；云安全组丢弃 443，大陆对未备案域名的 80 端口请求返回拦截页（`Server: Beaver`），因此不使用域名证书。应用容器继续只提供无状态 HTTP，当前试用入口为 `https://47.115.172.233:8080/`；明文 `http://47.115.172.233:8780` 只作负例，页面会精确提示缺的是安全上下文/WebCrypto。

