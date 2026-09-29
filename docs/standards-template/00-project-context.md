# 00 · 项目上下文 〔本项目活记忆 · AI 维护〕

> CONTROL-STATUS: draft · AUTHORITY: external-reference-template
> 本文件是参考模板，不是 amz-listing-kit 的真实项目上下文。

> **作用**:这是项目的“身份档案”。AI 接管项目时先读这里,了解项目目标、技术栈、目录、部署取值。
> **更新时机**:架构、技术栈、目录结构、端口、部署目录、重要约束变化时更新。
> **填写方式**:把 `<...>` 替换成真实内容;用不到的行删掉。

---

## 1. 项目是什么

- **项目名称**:`<项目名称>`
- **一句话目标**:`<这个项目要解决什么问题>`
- **使用者/受益者**:`<谁使用,为谁创造价值>`
- **核心功能**:
  - `<功能1>`
  - `<功能2>`
- **输入/数据**(如有):`<数据来源、规模、是否敏感、是否进 Git>`

## 2. 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 语言/运行时 | `<如 Python 3.11 / Node 20 / Java 17>` | `<为什么>` |
| Web/API 框架 | `<如 Flask / FastAPI / Express / Spring Boot>` | `<为什么>` |
| 测试 | `<如 pytest / jest / junit>` | `<为什么>` |
| 格式/静态检查 | `<如 ruff / eslint+prettier>` | `<为什么>` |
| 打包/运行 | `<如 Docker / 直接进程 / systemd>` | `<为什么>` |
| CI/CD | GitHub Actions | 通用、可视化、适合教学与团队协作 |

## 3. 目录地图

```text
<project>/
├── standards/                 # AI 项目记忆与通用规范
├── <源码目录>/                 # 如 app.py / src/ / backend/
├── <测试目录>/                 # 如 test_app.py / tests/
├── requirements.txt            # 生产运行依赖(如 Python 项目)
├── requirements-dev.txt        # 本地/CI 检查依赖(如 Python 项目)
├── Dockerfile                  # 如需要容器部署
├── .github/workflows/
│   ├── ci.yml
│   └── cd.yml
└── README.md
```

> 新增目录前先更新本节,避免项目越做越散。

## 4. 质量门槛

| 类型 | 本项目标准 |
|---|---|
| 格式检查 | `<如 ruff format --check .>` |
| 静态检查 | `<如 ruff check .>` |
| 单元测试 | `<如 pytest>` |
| 覆盖率 | `<如 >=80%;没有就写“暂无”>` |
| 构建 | `<如 docker build 成功>` |
| 业务/模型指标 | `<如接口成功率、模型指标、业务规则;没有就写“无”>` |

## 5. 不变约束

- 密钥、密码、私钥、Token **绝不写进代码或文档**,只进 GitHub Secrets / 环境变量。
- 大文件、数据集、模型产物是否进 Git,必须在本节写清楚;默认不进 Git。
- `main` 分支受保护,日常开发必须走 feature 分支 + PR。
- CI 红灯不合并。

## 6. 部署/CI 占位符取值

> `guides/` 和 workflow 里的通用占位符,在本项目里的真实值只写这里。

| 占位符 | 本项目取值 | 说明 |
|---|---|---|
| `<APP>` | `<应用名/镜像名/容器名>` | 如 `<app-name>` |
| `<DEPLOY_DIR>` | `<服务器部署目录>` | 如 `/opt/<app-name>` |
| `<PORT>` | `<服务端口>` | 如 `8000` |
| `<PYVER>` | `<Python/Node/Java 版本>` | 如 `3.11` |
| `<HEALTHCHECK>` | `<健康检查地址>` | 如 `/health` |
| `<SSH_USER>` | `<部署用户>` | 如 `root` 或 `deploy` |
| `<SSH_HOST>` | `<服务器公网 IP 或域名>` | 不写敏感信息以外的密钥 |
