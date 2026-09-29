FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/amz-listing-kit

# Product V2 当前运行时只需要标准库与正式静态资源；旧 V1、测试装置和冻结草案不进入镜像。
COPY app/server.py app/product_v2_server.py ./app/
COPY app/product_v2/ ./app/product_v2/

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /opt/amz-listing-kit

USER appuser
EXPOSE 8780

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/health', timeout=2)); raise SystemExit(0 if d.get('product') == 'v2' and d.get('server_state') == 'none' else 1)"

CMD ["python", "app/server.py", "--host", "0.0.0.0", "--port", "8780"]
