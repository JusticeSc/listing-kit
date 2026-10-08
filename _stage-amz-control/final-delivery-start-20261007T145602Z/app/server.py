# -*- coding: utf-8 -*-
r"""本地启动入口：默认 Product V2 正式入口；V1 与旧 fixture 为隔离回归分支。

常用命令
--------
    python app/server.py --open
    python app/server.py --check

Product V2（默认，端口 8780）：无状态服务器只提供页面与静态资源；项目、图片和历史全部保存在
浏览器 IndexedDB 中。服务器不保存工作空间、不保存最近项目，也没有 directory 之类的本机路径
参数。自检见 `python app/server.py --check`。本模块只做三件事：参数分发、V2 直接装配、
V1 / 旧 fixture 懒加载隔离分支；旧 fixture 实现在 `app/offline_fixture.py`（冻结归档），
正式 V2 与 V1 均不经过该模块，更不经过 `app/offline.py` / `app/views.py` / `demo/`。

历史入口（回归用，不进 V2 导航）
--------------------------------
    python app/server.py --legacy-v1 --open
    python app/server.py --legacy-v1 --check

Product V1 支持本地文件夹工作空间、商品资料录入、参考图保存与重开恢复、商品理解、套图方案、
提示词编辑、真实图片生成、单张返工、候选选择与导出；业务记录写入 WorkspaceStore，图片生成走
config/product-v1/providers.json 注册的图片模型。实现在 `app/product_v1_server.py`（本轮保留）。

旧回归入口
----------
    python app/server.py --offline-fixture demo/fixture/<商品包目录>
    python app/server.py --offline-fixture demo/fixture/<商品包目录> --check

旧入口固定使用 Mock，仅供 D2.R1 状态轨迹与零写入/零联网回归，不代表当前产品前端。
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True          # 必须在导入项目模块之前：否则 __pycache__ 会破坏上面第 1 条

import argparse              # noqa: E402
import socket                # noqa: E402
import subprocess            # noqa: E402
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


def run_doctor(host: str, port: int, legacy_v1: bool = False) -> int:
    """Check this machine can run the product; never starts a server or writes business files.

    默认检查 Product V2 正式入口；legacy_v1=True 时检查 Product V1 历史入口。
    """
    import importlib
    import json
    import os
    import tempfile

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

    if legacy_v1:
        required_files = [
            ROOT / "app" / "server.py",
            ROOT / "app" / "product_v1_server.py",
            ROOT / "src" / "product_prompt.py",
            ROOT / "config" / "product-v1" / "providers.json",
        ]
    else:
        required_files = [
            ROOT / "app" / "server.py",
            ROOT / "app" / "product_v2_server.py",
            ROOT / "app" / "product_v2" / "index.html",
            ROOT / "app" / "product_v2" / "entry.js",
            ROOT / "app" / "product_v2" / "app.js",
            ROOT / "app" / "product_v2" / "styles.css",
            ROOT / "app" / "product_v2" / "storage" / "index.js",
            ROOT / "config" / "product-v2" / "providers.json",
        ]
    missing = [str(item.relative_to(ROOT)) for item in required_files if not item.is_file()]
    if missing:
        add(
            "fail", "项目文件", "缺少：" + "、".join(missing),
            "在完整项目目录中运行（不要只拷走单个文件）",
        )
    elif legacy_v1:
        add("pass", "项目文件", "入口、服务与 provider 注册表齐全")
    else:
        add("pass", "项目文件", "入口、无状态适配器与 V2 产品资源齐全")

    missing_modules = []
    required_modules = ("PIL", "requests") if legacy_v1 else (
        "PIL", "requests", "pydantic", "langchain_openai")
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

    image_provider: dict | None = None
    if legacy_v1:
        registry_path = ROOT / "config" / "product-v1" / "providers.json"
        if registry_path.is_file():
            try:
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
            except Exception as exc:
                add("fail", "Provider 注册表", f"无法解析：{type(exc).__name__}",
                    "修复 config/product-v1/providers.json 的 JSON 语法")
            else:
                providers = {item.get("id"): item for item in registry.get("providers") or []}
                image_id = registry.get("default_image_provider_id")
                semantic_id = registry.get("default_semantic_provider_id")
                image_provider = providers.get(image_id)
                semantic_provider = providers.get(semantic_id)
                if (image_provider is None or image_provider.get("role") != "image"
                        or not image_provider.get("model_id")):
                    add("fail", "Provider 注册表",
                        f"默认图片 provider {image_id!r} 未注册或缺少 model_id",
                        "在 providers.json 中登记图片 provider（默认 qwen-image-3.0）")
                elif semantic_provider is None or semantic_provider.get("role") != "semantic":
                    add("fail", "Provider 注册表", f"默认语义 provider {semantic_id!r} 未注册",
                        "在 providers.json 中登记语义 provider")
                else:
                    add("pass", "Provider 注册表",
                        f"图片 {image_id} / {image_provider.get('model_id')}；"
                        f"语义 {semantic_id} / {semantic_provider.get('model_id')}")

        key_env = (image_provider or {}).get("api_key_env") or "DASHSCOPE_API_KEY"
        if os.environ.get(key_env):
            add("pass", "模型凭据", f"已设置 {key_env}")
        else:
            add("warn", "模型凭据",
                f"未设置 {key_env}；页面能打开、方案能生成，但一键出图会失败",
                f'设置后重开终端：setx {key_env} "sk-..."')
    else:
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

    if legacy_v1:
        from app.product_v1_server import _default_recent_index_path

        index_dir = _default_recent_index_path().parent
        base = index_dir if index_dir.exists() else index_dir.parent
        writable = False
        try:
            with tempfile.NamedTemporaryFile(dir=base, prefix="amz-doctor-", delete=True):
                writable = True
        except Exception:
            writable = False
        if writable:
            add("pass", "工作空间索引目录",
                f"{index_dir} 可写" if index_dir.exists() else f"{index_dir} 将在首次使用时创建")
        else:
            add("fail", "工作空间索引目录", f"{index_dir} 不可写",
                "检查目录权限；产品仍可运行，但最近工作空间列表无法保存")
    else:
        add("pass", "用户数据位置",
            "Product V2 的项目与图片保存在浏览器 IndexedDB；服务器没有工作空间目录，"
            "也不写最近项目索引")

    print("=" * 72)
    product_label = "Product V1 历史入口" if legacy_v1 else "Product V2 正式入口"
    print(f"AMZ Listing Kit doctor（{product_label}；只检查，不修改任何业务文件）")
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


def check_product_v1() -> int:
    """Run the real Product V1 HTTP slice checks without modifying this checkout."""
    check_script = ROOT / "tools" / "verify_product_v1_http.py"
    if not check_script.is_file():
        print("Product V1 自检文件缺失：tools/verify_product_v1_http.py")
        return 2
    print("Product V1 自检：工作空间 HTTP 闭环")
    return subprocess.run(
        [sys.executable, "-B", str(check_script)], cwd=str(ROOT), check=False,
    ).returncode


def check_product_v2() -> int:
    """Run the Product V2 formal-entry self-check; no model call, no file writes."""
    from app.product_v2_server import run_self_check

    print("Product V2 自检：无状态正式入口")
    return run_self_check()


def serve_product_v2(args) -> int:
    """Start the default Product V2 entry: static product shell, browser-owned state."""
    from app.product_v2_server import create_product_v2_server

    try:
        httpd = create_product_v2_server(args.host, args.port)
    except OSError as exc:
        detail = str(exc.strerror or exc).strip().rstrip("。.")
        print(f"端口 {args.port} 用不了：{detail}。")
        print(f"换一个端口再启动，例如：python app/server.py --port {args.port + 1}")
        return 3

    url = f"http://{args.host}:{args.port}/"
    print("本地商品套图工作台（Product V2）：" + url)
    if args.host in {"0.0.0.0", "::"}:
        try:
            lan = socket.gethostbyname(socket.gethostname())
            print(f"局域网/内网穿透访问：http://{lan}:{args.port}/")
        except OSError:
            pass
    print("项目与历史保存在这台浏览器里；服务器不保存工作空间，也不保存最近项目记录。")
    print("商品资料、事实确认、套图生成、比较返工和交付均通过浏览器工作台操作。")
    print("按 Ctrl+C 停止。")
    if args.open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


def run_offline_fixture(args) -> int:
    """旧离线 Mock 回归分支：实现在冻结归档模块，正式 V2/V1 不经过这里。"""
    try:
        from app.offline_fixture import run
    except ModuleNotFoundError:
        print("当前生产镜像只含 Product V2 正式入口；旧离线回归不在镜像里，"
              "请在完整仓库用 --offline-fixture 运行。")
        return 2

    return run(args)


def serve_product_v1(args) -> int:
    """Start the explicitly retained Product V1 entry."""
    try:
        from app.product_v1_server import create_product_server
    except ModuleNotFoundError:
        print("当前生产镜像只含 Product V2 正式入口；V1 历史入口不在镜像里，"
              "请在完整仓库用 --legacy-v1 运行。")
        return 2

    try:
        httpd = create_product_server(args.host, args.port)
    except ValueError as exc:
        print(str(exc))
        return 2
    except OSError as exc:
        detail = str(exc.strerror or exc).strip().rstrip("。.")
        print(f"端口 {args.port} 用不了：{detail}。")
        print(f"换一个端口再启动，例如：python app/server.py --port {args.port + 1}")
        return 3

    url = f"http://{args.host}:{args.port}/"
    print("本地商品套图工作台：" + url)
    print("覆盖流程：资料 → 商品理解 → 套图方案 → 提示词 → 真实出图 → 单张返工 → 选择 → 导出。")
    print("图片模型取决于本地 DASHSCOPE_API_KEY 与网络；未配置时页面会给出可执行的修复提示。")
    print("按 Ctrl+C 停止。")
    if args.open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="本地商品套图工作台（默认 Product V2 无状态入口；"
                    "--legacy-v1 回 Product V1；--offline-fixture 保留旧 Mock 回归）"
    )
    ap.add_argument("--legacy-v1", action="store_true",
                    help="启动 Product V1 历史入口（文件夹工作空间 + 最近项目索引）")
    ap.add_argument("--offline-fixture", default=None,
                    help="启动旧离线 Mock 回归页面，例如 demo/fixture/<包名>")
    ap.add_argument("--project", default=str(ROOT))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=None,
                    help="监听端口（Product V2/V1 默认 8780，旧 Mock 默认 8778）")
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    ap.add_argument("--check", action="store_true",
                    help="只跑对应自检：Product V2/V1 HTTP 闭环或旧 Mock 离线检查")
    ap.add_argument("--doctor", action="store_true",
                    help="只检查本机能否运行产品（不启动服务、不修改业务文件）")
    args = ap.parse_args(argv)
    if args.port is None:
        args.port = 8778 if args.offline_fixture else 8780
    if args.offline_fixture:
        return run_offline_fixture(args)
    if args.legacy_v1:
        if args.doctor:
            return run_doctor(args.host, args.port, legacy_v1=True)
        return check_product_v1() if args.check else serve_product_v1(args)
    if args.doctor:
        return run_doctor(args.host, args.port)
    return check_product_v2() if args.check else serve_product_v2(args)


if __name__ == "__main__":
    raise SystemExit(main())
