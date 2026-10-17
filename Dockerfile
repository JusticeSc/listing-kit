# Product V2 生产镜像（SEL-023/SEL-025）：Python 无状态网关 + Vite 标准构建产物。
#
# 阶段：
#   python-deps     锁依赖 venv（pyproject.toml + uv.lock，--no-dev）：schema 导出与
#                   运行时共用这一层，构建只下载一次锁定 wheel。
#   envelope-schema 信封 schema 构建期导出：从 src/providers/v2_image.py 导出唯一结构投影。
#                   domain/generated/ 是 gitignored 构建产物，干净检出没有，必须在这里重建。
#   frontend        Node 锁依赖（package.json engines：node 24.19.0 / npm 11.17.0）生成
#                   validator 并执行 Vite 标准构建，产出 dist/product-v2。
#   runtime（末段） 正式运行闭包：4 个入口 Python 文件 + src/config 白名单 + 构建产物。
#                   无 Node、无前端源码、无测试替身、无 dev 依赖；缺 dist 即启动失败。
FROM python:3.13-slim-bookworm AS python-deps

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


FROM python-deps AS envelope-schema

# 结构权威是 src/providers/v2_image.py 的 ImageWire* 模型；只导出，不校验业务。
COPY src/ ./src/
COPY tools/export_image_envelope_schema.py ./tools/export_image_envelope_schema.py
RUN python tools/export_image_envelope_schema.py --out /out/image-task-envelope.schema.json


FROM node:24.19.0-bookworm-slim AS frontend

WORKDIR /build
# npm 安装禁 scripts（与 CI 同策略）；版本由 package.json engines 钉死。
COPY package.json package-lock.json ./
RUN npm install --global "npm@$(node -p 'require("./package.json").engines.npm')" --ignore-scripts --no-audit --no-fund \
    && npm ci --ignore-scripts --no-audit --no-fund
COPY app/product_v2/ ./app/product_v2/
COPY vite.config.mjs tsconfig.json ./
COPY tools/generate_image_envelope_validator.mjs ./tools/generate_image_envelope_validator.mjs
COPY --from=envelope-schema /out/image-task-envelope.schema.json ./app/product_v2/domain/generated/image-task-envelope.schema.json
RUN npm run build:envelope-validator && npm run build:frontend


FROM python-deps AS runtime

WORKDIR /opt/amz-listing-kit

# app/ 用显式文件 COPY：.dockerignore 必须放行完整前端源码给构建器，运行时只取这 4 个；
# src/ 与 config/ 用目录 COPY + .dockerignore 白名单（假 provider 物理排除，verification.json 不进镜像）。
COPY app/__init__.py app/server.py app/product_v2_server.py app/product_v2_http.py ./app/
COPY src/ ./src/
COPY config/ ./config/
COPY --from=frontend /build/dist/product-v2/ ./dist/product-v2/

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /opt/amz-listing-kit

USER appuser
EXPOSE 8780

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health', timeout=2)); raise SystemExit(0 if d.get('product') == 'v2' and d.get('server_state') == 'none' else 1)"

CMD ["python", "app/server.py", "--host", "0.0.0.0", "--port", "8780"]
