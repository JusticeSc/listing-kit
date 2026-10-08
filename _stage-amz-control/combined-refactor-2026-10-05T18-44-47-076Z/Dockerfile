FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/amz-listing-kit/.venv \
    UV_LINK_MODE=copy \
    PATH=/opt/amz-listing-kit/.venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

# 依赖权威是 pyproject.toml + uv.lock：镜像里也用同一套锁定依赖装，不用 pip 手写清单。
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /bin/

WORKDIR /opt/amz-listing-kit

# 先装依赖再放代码：改产品代码不会让依赖层失效。
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Product V2 运行时:正式入口、产品静态资源、语义 provider 注册表与两个无状态 API 的依赖。
# 旧 V1 代码、测试装置(evals/)、冻结草案与工作记录不进入镜像。
# 渐进 TS 迁移(计划 §9 V2.R7.5):domain/*.ts 与 .d.ts 由 .dockerignore 排除,镜像里只带
# `npm run build:frontend` 生成的同目录 .js;生产运行时没有 TS 编译器,也没有第二份源码。
COPY app/server.py app/product_v2_server.py ./app/
COPY app/product_v2/ ./app/product_v2/
COPY src/ ./src/
COPY config/ ./config/

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /opt/amz-listing-kit

USER appuser
EXPOSE 8780

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health', timeout=2)); raise SystemExit(0 if d.get('product') == 'v2' and d.get('server_state') == 'none' else 1)"

CMD ["python", "app/server.py", "--host", "0.0.0.0", "--port", "8780"]
