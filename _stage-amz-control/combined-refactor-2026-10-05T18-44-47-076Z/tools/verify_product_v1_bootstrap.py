#!/usr/bin/env python
"""Guard Product V1 startup/check from importing the legacy Mock stack."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = r"""
import builtins
import sys

sys.path.insert(0, sys.argv[1])
legacy_modules = {"app.offline", "app.views"}
real_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name in legacy_modules or (name == "app" and legacy_modules.intersection(fromlist)):
        raise AssertionError(f"Product V1 startup imported legacy module: {name} {fromlist}")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import
import app.server as server
import app.product_v1_server as product_v1_server

class ProductLaunchReached(Exception):
    pass

def capture_product_launch(host, port):
    if (host, port) != ("127.0.0.1", 8780):
        raise AssertionError(f"unexpected default Product V1 launch args: {host} {port}")
    raise ProductLaunchReached()

product_v1_server.create_product_server = capture_product_launch
try:
    server.main([])
except ProductLaunchReached:
    pass
else:
    raise AssertionError("default startup did not reach the Product V1 server")

if legacy_modules.intersection(sys.modules):
    raise AssertionError("Product V1 startup loaded a legacy fixture module")

raise SystemExit(server.main(["--check"]))
"""


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-B", "-c", PROBE, str(ROOT)],
        cwd=ROOT,
        check=False,
    )
    if result.returncode:
        print(f"Product V1 bootstrap 回归失败（退出码 {result.returncode}）")
    else:
        print("Product V1 bootstrap 回归通过：--check 未导入旧 Mock 栈")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
