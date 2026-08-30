"""网络分区容错：Agent 断连时本地缓存截图，重连后补传"""
import json
import logging
import os
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class OfflineCache:
    """离线缓存管理器"""

    def __init__(self, cache_dir: str = "./cache/offline"):
        """初始化离线缓存

        Args:
            cache_dir: 缓存目录路径
        """
        self.cache_dir = cache_dir
        self._ensure_dir()

    def _ensure_dir(self):
        """确保缓存目录存在"""
        os.makedirs(self.cache_dir, exist_ok=True)

    def cache_screenshot(self, execution_id: str, step_index: int, image_data: bytes):
        """缓存截图到本地

        Args:
            execution_id: 执行ID
            step_index: 步骤索引
            image_data: 图片二进制数据

        Returns:
            缓存文件路径
        """
        filename = f"{execution_id}_{step_index}_{int(time.time() * 1000)}.png"
        filepath = os.path.join(self.cache_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(image_data)
        self._record_cache(execution_id, step_index, filepath)
        return filepath

    def _record_cache(self, execution_id: str, step_index: int, filepath: str):
        """记录缓存索引

        Args:
            execution_id: 执行ID
            step_index: 步骤索引
            filepath: 缓存文件路径
        """
        index_path = os.path.join(self.cache_dir, f"{execution_id}.index")
        record = {
            'execution_id': execution_id,
            'step_index': step_index,
            'filepath': filepath,
            'cached_at': datetime.now().isoformat(),
        }
        with open(index_path, 'a') as f:
            f.write(json.dumps(record) + '\n')

    def get_pending_uploads(self, execution_id: str) -> list:
        """获取待补传的截图列表

        Args:
            execution_id: 执行ID

        Returns:
            待补传记录列表
        """
        index_path = os.path.join(self.cache_dir, f"{execution_id}.index")
        if not os.path.exists(index_path):
            return []
        records = []
        with open(index_path) as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line.strip()))
        return records

    def flush(self, execution_id: str, upload_fn):
        """补传所有离线缓存的截图

        Args:
            execution_id: 执行ID
            upload_fn: 上传回调函数，签名为 (execution_id, step_index, image_data) -> None
        """
        pending = self.get_pending_uploads(execution_id)
        for record in pending:
            try:
                filepath = record['filepath']
                if os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        upload_fn(
                            execution_id=record['execution_id'],
                            step_index=record['step_index'],
                            image_data=f.read(),
                        )
                    os.remove(filepath)
            except Exception as e:
                logger.warning("补传截图失败 %s: %s", record['filepath'], e)
        index_path = os.path.join(self.cache_dir, f"{execution_id}.index")
        if os.path.exists(index_path):
            os.remove(index_path)

    def clear(self, execution_id: str):
        """清除指定执行的缓存

        Args:
            execution_id: 执行ID
        """
        index_path = os.path.join(self.cache_dir, f"{execution_id}.index")
        if os.path.exists(index_path):
            pending = self.get_pending_uploads(execution_id)
            for record in pending:
                if os.path.exists(record['filepath']):
                    os.remove(record['filepath'])
            os.remove(index_path)
