FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/amz-listing-kit/.venv \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    UV_HTTP_RETRIES=5 \
    PATH=/opt/amz-listing-kit/.venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

# 依赖权威是 pyproject.toml + uv.lock：镜像里也用同一套锁定依赖装，不用 pip 手写清单。
# UV_HTTP_* 只影响构建期从 pyproject 固定的镜像索引取锁定 wheel（运行时 CMD 用 python，不经 uv）：
# 2026-10-08 CI run 37760499569 在 `uv sync` 拉 pillow 12.3.0 / numpy(15.9MiB) 时按 uv 默认
# 30s 每请求超时失败（`Failed to download distribution due to network timeout. Try increasing
# UV_HTTP_TIMEOUT (current value: 30s)`），同一 tree 的上一轮构建通过 ⇒ 是下载层超时，不是产品行为。
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /bin/

WORKDIR /opt/amz-listing-kit

# 先装依赖再放代码：改产品代码不会让依赖层失效。
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Product V2 运行时:正式入口、产品静态资源、V2 provider 注册表/适配器与无状态网关的依赖。
# 目录 COPY + .dockerignore 排除旧业务(无字面文件钉):V1入口/旧fixture归档与实现/旧tracer、
# V1适配器(src/providers非v2_*)、V1业务核心、旧config均不在镜像里。
# 导入集合从当前代码推导:product_v2_server只触及src/console.py与src/providers/{__init__,v2_*}、
# 其第三方依赖(requests/Pillow/langchain/pydantic,见uv.lock)与config/product-v2/providers.json;
# config/product-v2/verification.json 只服务 CI 登记校验，由 .dockerignore 排除。
# 旧 fixture 归档(app/offline_fixture.py)只服务本地回归,不进镜像。
# 渐进 TS 迁移(计划 §9 V2.R7.5):domain/*.ts 与 .d.ts 由 .dockerignore 排除,镜像里只带
# `npm run build:frontend` 生成的同目录 .js;生产运行时没有 TS 编译器,也没有第二份源码。
COPY app/ ./app/
COPY src/ ./src/
COPY config/ ./config/

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /opt/amz-listing-kit

USER appuser
EXPOSE 8780

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health', timeout=2)); raise SystemExit(0 if d.get('product') == 'v2' and d.get('server_state') == 'none' else 1)"

CMD ["python", "app/server.py", "--host", "0.0.0.0", "--port", "8780"]
