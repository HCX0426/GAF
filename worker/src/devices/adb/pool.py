"""ADB 连接池

复用 adbutils.AdbDevice 对象，避免每次调用 adb.device() 的开销。
线程安全，支持连接健康检查和自动重连。

Usage:
    from adb.pool import AdbPool
    pool = AdbPool()
    device = pool.get("127.0.0.1:62001")
    device.screencap()
    pool.release("127.0.0.1:62001")
"""

import logging
import threading

logger = logging.getLogger(__name__)


class AdbPool:
    """ADB 连接池（单例模式）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> "AdbPool":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # 延迟初始化，避免在 import 时触发 adbutils 导入。
        # Guarded so repeated __init__ (triggered by singleton reuse) does
        # not reset an already-populated pool.
        if getattr(self, "_core_initialized", False):
            return
        self._core_initialized = True
        self._initialized = False
        self._pool: dict[str, object] = {}  # serial -> AdbDevice
        self._lock_pool = threading.Lock()

    def _ensure_initialized(self) -> bool:
        """确保 adbutils 已导入"""
        if not self._initialized:
            try:
                from adbutils import adb  # noqa: F401
                self._initialized = True
            except ImportError:
                logger.warning("adbutils 库未安装，ADB 连接池不可用")
                return False
        return True

    def get(self, serial: str) -> object | None:
        """获取 ADB 设备连接

        Args:
            serial: ADB 设备序列号

        Returns:
            AdbDevice 对象，失败返回 None
        """
        if not self._ensure_initialized():
            return None

        from adbutils import adb

        with self._lock_pool:
            # 检查缓存的连接是否仍然有效
            if serial in self._pool:
                device = self._pool[serial]
                try:
                    # 简单健康检查：尝试获取设备属性
                    device.shell("echo", timeout=2)
                    logger.debug("ADB 连接池命中: %s", serial)
                    return device
                except Exception as e:
                    logger.debug("ADB 连接池: %s 连接失效，移除: %s", serial, e)
                    del self._pool[serial]

            # 建立新连接
            try:
                device = adb.device(serial)
                self._pool[serial] = device
                logger.info("ADB 连接池: 新建连接 %s", serial)
                return device
            except Exception as e:
                logger.error("ADB 连接池: 创建 %s 连接失败: %s", serial, e)
                return None

    def release(self, serial: str) -> None:
        """释放指定设备的连接（从池中移除）

        Args:
            serial: ADB 设备序列号
        """
        with self._lock_pool:
            if serial in self._pool:
                del self._pool[serial]
                logger.debug("ADB 连接池: 释放 %s", serial)

    def release_all(self) -> None:
        """释放所有连接"""
        with self._lock_pool:
            count = len(self._pool)
            self._pool.clear()
            if count > 0:
                logger.info("ADB 连接池: 释放全部连接 (%d 个)", count)

    def list_serials(self) -> list:
        """列出池中所有已缓存的序列号"""
        with self._lock_pool:
            return list(self._pool.keys())


# 全局单例
_pool: AdbPool | None = None
_pool_lock = threading.Lock()


def get_adb_pool() -> AdbPool:
    """获取全局 ADB 连接池单例"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = AdbPool()
    return _pool
