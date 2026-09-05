"""P0-2/D2 (评审 2026-09-05): 校验 config.settings.prod 可完整导入。

背景: CI 环境走 environment.yml -> requirements/dev.txt, 从未导入过
config.settings.prod — whitenoise 类依赖漂移（"requirements 有、pyproject
无"）只能等到裸机部署首个请求才 ModuleNotFoundError, django.setup() 的
"配置加载成功"假象会掩盖缺陷。

本脚本 django.setup() 后逐个 import 中间件类与静态存储后端,
任何一个缺失即非零退出。需先安装 prod 专有依赖 (whitenoise):

    pip install "whitenoise>=6.7,<7.0"
    set DJANGO_SETTINGS_MODULE=config.settings.prod
    set SECRET_KEY=ci-check-not-real
    python scripts/check_prod_settings.py   (cwd = backend/)
"""

import os
import sys
from importlib import import_module


def _import_class(dotted_path: str) -> None:
    """import a.b.Class 形式的类, 失败抛原异常。"""
    module_path, _, cls_name = dotted_path.rpartition(".")
    getattr(import_module(module_path), cls_name)


def main() -> int:
    # 运行方式约定: cwd=backend/ (如 `python ../scripts/check_prod_settings.py`)。
    # 按路径执行脚本时 sys.path[0] 是脚本所在目录而非 CWD, 手动补上 CWD
    # 才能导入 backend/ 下的 config 包。
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    # base.py 对 DEBUG=False + 默认 SECRET_KEY 会 fail-fast (TD-334);
    # 本校验只需配置可加载, 给一个非默认 key 即可。
    os.environ.setdefault("SECRET_KEY", "ci-prod-config-check-not-a-real-key")
    os.environ.setdefault("ALLOWED_HOSTS", "localhost")

    import django

    django.setup()

    from django.conf import settings

    failures = []

    for mw_path in settings.MIDDLEWARE:
        try:
            _import_class(mw_path)
        except Exception as exc:
            failures.append(f"middleware 不可导入: {mw_path}: {exc!r}")

    storages = getattr(settings, "STORAGES", {}) or {}
    backend = (storages.get("staticfiles") or {}).get("BACKEND") or getattr(
        settings, "STATICFILES_STORAGE", ""
    )
    if backend:
        try:
            _import_class(backend)
        except Exception as exc:
            failures.append(f"staticfiles backend 不可导入: {backend}: {exc!r}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print(
        f"prod settings OK: {len(settings.MIDDLEWARE)} middleware, "
        f"staticfiles backend = {backend}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
