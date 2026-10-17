# -*- coding: utf-8 -*-
r"""本地启动入口：Product V2 正式入口（唯一可执行产品）。

常用命令
--------
    python app/server.py --open
    python app/server.py --check

Product V2（默认，端口 8780）：无状态服务器只提供页面与静态资源；项目、图片和历史全部保存在
浏览器 IndexedDB 中。服务器不保存工作空间、不保存最近项目，也没有 directory 之类的本机路径
参数。自检见 `python app/server.py --check`。本模块只做两件事：参数分发、V2 直接装配。

已退役入口
----------
V1（Product V1 文件夹工作空间）与旧离线 Mock 回归分支已随 main 基线 P1 退出仓库，
不再提供 `--legacy-v1` / `--offline-fixture` / `--project` 参数；旧能力不可回退启动。
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True          # 必须在导入项目模块之前：否则 __pycache__ 会破坏上面第 1 条

import argparse              # noqa: E402
import socket                # noqa: E402
import webbrowser            # noqa: E402
from pathlib import Path     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # 控制台编码归一（项目约定：每个入口自己保证中文输出不炸）
    from src.console import enable_utf8

    enable_utf8()
except Exception:  # 归一化失败不该让入口起不来
    pass


def run_doctor(host: str, port: int) -> int:
    """Check this machine can run the product; never starts a server or writes business files.

    只检查 Product V2 正式入口。
    """
    import importlib

    results: list[tuple[str, str, str, str]] = []

    def add(status: str, name: str, detail: str, fix: str = "") -> None:
        results.append((status, name, detail, fix))

    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        add("pass", "Python", f"{version}（{sys.executable}）")
    else:
        add(
            "fail", "Python", f"{version} 过低（需要 3.10 以上）",
            "安装 Python 3.10+；在项目根目录用 uv 启动：uv run --locked python app/server.py --doctor",
        )

    required_files = [
        ROOT / "app" / "server.py",
        ROOT / "app" / "product_v2_server.py",
        ROOT / "app" / "product_v2_http.py",
        ROOT / "config" / "product-v2" / "providers.json",
    ]
    missing = [str(item.relative_to(ROOT)) for item in required_files if not item.is_file()]
    if missing:
        add(
            "fail", "项目文件", "缺少：" + "、".join(missing),
            "在完整项目目录中运行（不要只拷走单个文件）",
        )
    else:
        add("pass", "项目文件", "入口、无状态适配器与 provider 注册表齐全")

    static_index = ROOT / "dist" / "product-v2" / "index.html"
    if static_index.is_file():
        add("pass", "前端产物", "唯一静态产物 dist/product-v2 已构建")
    else:
        add(
            "fail", "前端产物", "缺少 dist/product-v2/index.html（生产网关只服务构建产物）",
            "在项目根目录运行前端构建：npm ci --ignore-scripts && npm run build:frontend",
        )

    missing_modules = []
    required_modules = ("fastapi", "uvicorn", "requests", "pydantic", "langchain_openai")
    for module in required_modules:
        try:
            importlib.import_module(module)
        except Exception:
            missing_modules.append(module)
    if missing_modules:
        add(
            "fail", "运行依赖", "不能导入：" + "、".join(missing_modules),
            "安装依赖：uv sync --locked（或在项目根目录 uv run --locked python app/server.py）",
        )
    else:
        add("pass", "运行依赖", "锁定运行依赖可导入：" + "、".join(required_modules))

    add("pass", "模型接入",
        "商品理解、生图和复核均由用户明确发起；客户端按用途配置自己的 key，"
        "默认付费档缺省关闭，不配置理解/复核 key 仍可走人工事实与采用路径。")

    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        busy = probe.connect_ex((host, port)) == 0
    if busy:
        add("fail", "端口", f"{host}:{port} 已被占用",
            f"换一个端口启动：python app/server.py --port {port + 1} --open")
    else:
        add("pass", "端口", f"{host}:{port} 可用")

    add("pass", "用户数据位置",
        "Product V2 的项目与图片保存在浏览器 IndexedDB；服务器没有工作空间目录，"
        "也不写最近项目索引")

    print("=" * 72)
    print("AMZ Listing Kit doctor（Product V2 正式入口；只检查，不修改任何业务文件）")
    print("=" * 72)
    labels = {"pass": "通过", "warn": "注意", "fail": "未通过"}
    for status, name, detail, fix in results:
        print(f"[{labels[status]}] {name}：{detail}")
        if fix:
            print(f"         修复：{fix}")
    failures = [item for item in results if item[0] == "fail"]
    warnings = [item for item in results if item[0] == "warn"]
    print("-" * 72)
    if failures:
        print(f"结果：暂不能启动（{len(failures)} 项未通过，{len(warnings)} 条提醒）。"
              "按上面的修复步骤处理后重试。")
        return 2
    print(f"结果：可以启动（{len(warnings)} 条提醒）。")
    if warnings:
        print("      提醒项不阻止启动；真实出图前先处理模型凭据。")
    return 0


def check_product_v2() -> int:
    """Run the Product V2 formal-entry self-check; no model call, no file writes."""
    from app.product_v2_server import run_self_check

    print("Product V2 轻量自检：无状态正式入口（真实 TCP 健康检查 + 唯一构建产物）")
    return run_self_check()


def serve_product_v2(args) -> int:
    """Start the default Product V2 entry: static product shell, browser-owned state."""
    from app.product_v2_http import StaticRootMissing
    from app.product_v2_server import create_product_v2_server

    try:
        server = create_product_v2_server(args.host, args.port)
    except StaticRootMissing as exc:
        print(str(exc))
        return 2
    except OSError as exc:
        detail = str(exc.strerror or exc).strip().rstrip("。.")
        print(f"端口 {args.port} 用不了：{detail}。")
        print(f"换一个端口再启动，例如：python app/server.py --port {args.port + 1}")
        return 3

    url = f"http://{args.host}:{server.port}/"
    print("本地商品套图工作台（Product V2）：" + url)
    if args.host in {"0.0.0.0", "::"}:
        try:
            lan = socket.gethostbyname(socket.gethostname())
            print(f"局域网/内网穿透访问：http://{lan}:{server.port}/")
        except OSError:
            pass
    print("项目与历史保存在这台浏览器里；服务器不保存工作空间，也不保存最近项目记录。")
    print("商品资料、事实确认、套图生成、比较返工和交付均通过浏览器工作台操作。")
    print("按 Ctrl+C 停止。")
    if args.open:
        webbrowser.open(url)
    try:
        server.run()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.stop()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="本地商品套图工作台（Product V2 无状态入口）"
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8780,
                    help="监听端口（默认 8780）")
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    ap.add_argument("--check", action="store_true",
                    help="只跑 Product V2 正式入口自检（不启动服务）")
    ap.add_argument("--doctor", action="store_true",
                    help="只检查本机能否运行产品（不启动服务、不修改业务文件）")
    args = ap.parse_args(argv)
    if args.doctor:
        return run_doctor(args.host, args.port)
    return check_product_v2() if args.check else serve_product_v2(args)


if __name__ == "__main__":
    raise SystemExit(main())
