"""OCR 双引擎集成单元测试"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from engine.nodes.ocr import OCRNode
from recognition.cache import OCRResultCache
from recognition.ocr import BaseOCREngine
from recognition.ocr.registry import OCREngineRegistry
from recognition.ocr.types import OCRResult

pytestmark = pytest.mark.unit


class TestOCRResult:
    """OCRResult 数据类型测试"""

    def test_create_ocr_result(self):
        """验证 OCRResult 创建"""
        result = OCRResult(text="你好", confidence=0.95, box=(10, 20, 100, 50))
        assert result.text == "你好"
        assert result.confidence == 0.95
        assert result.box == (10, 20, 100, 50)

    def test_ocr_result_defaults(self):
        """验证 OCRResult 各字段类型正确"""
        result = OCRResult(text="", confidence=0.0, box=(0, 0, 0, 0))
        assert isinstance(result.text, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.box, tuple)

    def test_ocr_result_is_dataclass(self):
        """验证 OCRResult 是 dataclass，支持相等比较"""
        a = OCRResult(text="test", confidence=0.8, box=(0, 0, 10, 10))
        b = OCRResult(text="test", confidence=0.8, box=(0, 0, 10, 10))
        assert a == b


class MockEngine(BaseOCREngine):
    """用于测试的模拟 OCR 引擎"""

    def __init__(self, results=None, languages=None):
        self._results = results or []
        self._languages = languages or ["ch", "en"]

    def recognize(self, image, lang="ch"):
        return self._results

    def available_languages(self):
        return self._languages


class TestBaseOCREngine:
    """BaseOCREngine 抽象基类测试"""

    def test_cannot_instantiate_abstract(self):
        """验证抽象基类不可直接实例化"""
        with pytest.raises(TypeError):
            BaseOCREngine()

    def test_concrete_subclass_works(self):
        """验证实现了抽象方法的子类可正常实例化和使用"""
        engine = MockEngine()
        results = engine.recognize(np.zeros((100, 100, 3), dtype=np.uint8))
        assert isinstance(results, list)
        assert engine.available_languages() == ["ch", "en"]


class TestPaddleOCREngine:
    """PaddleOCREngine 测试"""

    def test_import_error_graceful_degradation(self):
        """验证 PaddleOCR 不可用时抛出明确异常"""
        with patch.dict("sys.modules", {"paddleocr": None}):
            from recognition.ocr.paddle_engine import PaddleOCREngine

            engine = PaddleOCREngine()
            with pytest.raises(ImportError, match="PaddleOCR"):
                engine._ensure_engine()

    def test_lazy_loading(self):
        """验证懒加载：初始化时不创建 PaddleOCR 实例"""
        from recognition.ocr.paddle_engine import PaddleOCREngine

        engine = PaddleOCREngine()
        assert engine._engine is None

    def test_available_languages(self):
        """验证返回支持的语言列表"""
        from recognition.ocr.paddle_engine import PaddleOCREngine

        engine = PaddleOCREngine()
        langs = engine.available_languages()
        assert "ch" in langs
        assert "en" in langs

    def test_recognize_with_mock(self):
        """验证 recognize 正确转换 PaddleOCR 输出为 OCRResult 列表"""
        from recognition.ocr.paddle_engine import PaddleOCREngine

        mock_engine = MagicMock()
        mock_engine.ocr.return_value = [[
            [
                [[10, 20], [100, 20], [100, 50], [10, 50]],
                ("测试文本", 0.95),
            ],
            [
                [[30, 60], [90, 60], [90, 80], [30, 80]],
                ("第二行", 0.88),
            ],
        ]]

        engine = PaddleOCREngine()
        engine._engine = mock_engine

        image = np.zeros((200, 200, 3), dtype=np.uint8)
        results = engine.recognize(image)

        assert len(results) == 2
        assert results[0].text == "测试文本"
        assert results[0].confidence == 0.95
        assert results[0].box == (10, 20, 100, 50)
        assert results[1].text == "第二行"
        assert results[1].confidence == 0.88

    def test_recognize_empty_result(self):
        """验证空结果返回空列表"""
        from recognition.ocr.paddle_engine import PaddleOCREngine

        mock_engine = MagicMock()
        mock_engine.ocr.return_value = None

        engine = PaddleOCREngine()
        engine._engine = mock_engine

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        results = engine.recognize(image)
        assert results == []


class TestRapidOCREngine:
    """RapidOCREngine 测试"""

    def test_import_error_graceful_degradation(self):
        """验证 RapidOCR 不可用时抛出明确异常"""
        with patch.dict("sys.modules", {"rapidocr_onnxruntime": None}):
            from recognition.ocr.rapid_engine import RapidOCREngine

            engine = RapidOCREngine()
            with pytest.raises(ImportError, match="RapidOCR"):
                engine._ensure_engine()

    def test_lazy_loading(self):
        """验证懒加载：初始化时不创建 RapidOCR 实例"""
        from recognition.ocr.rapid_engine import RapidOCREngine

        engine = RapidOCREngine()
        assert engine._engine is None

    def test_available_languages(self):
        """验证返回支持的语言列表"""
        from recognition.ocr.rapid_engine import RapidOCREngine

        engine = RapidOCREngine()
        langs = engine.available_languages()
        assert "ch" in langs
        assert "en" in langs

    def test_recognize_with_mock(self):
        """验证 recognize 正确转换 RapidOCR 输出为 OCRResult 列表"""
        from recognition.ocr.rapid_engine import RapidOCREngine

        mock_engine = MagicMock()
        mock_engine.return_value = (
            [
                [[[10, 20], [100, 20], [100, 50], [10, 50]], "快速文本", 0.92],
                [[[30, 60], [90, 60], [90, 80], [30, 80]], "第二结果", 0.85],
            ],
            None,
        )

        engine = RapidOCREngine()
        engine._engine = mock_engine

        image = np.zeros((200, 200, 3), dtype=np.uint8)
        results = engine.recognize(image)

        assert len(results) == 2
        assert results[0].text == "快速文本"
        assert results[0].confidence == 0.92
        assert results[0].box == (10, 20, 100, 50)
        assert results[1].text == "第二结果"
        assert results[1].confidence == 0.85

    def test_recognize_empty_result(self):
        """验证空结果返回空列表"""
        from recognition.ocr.rapid_engine import RapidOCREngine

        mock_engine = MagicMock()
        mock_engine.return_value = (None, None)

        engine = RapidOCREngine()
        engine._engine = mock_engine

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        results = engine.recognize(image)
        assert results == []


class TestOCREngineRegistry:
    """OCREngineRegistry 引擎注册表测试"""

    def test_register_engine(self):
        """验证引擎注册"""
        registry = OCREngineRegistry()
        engine = MockEngine()
        registry.register(engine, "mock")
        assert "mock" in registry.engine_names

    def test_register_duplicate_warns(self):
        """验证重复注册不抛出异常，引擎被覆盖"""
        registry = OCREngineRegistry()
        engine1 = MockEngine()
        engine2 = MockEngine()
        registry.register(engine1, "mock")
        registry.register(engine2, "mock")
        assert registry.get_engine("mock") is engine2

    def test_benchmark_no_engines_raises(self):
        """验证无引擎时 benchmark 抛出异常"""
        registry = OCREngineRegistry()
        with pytest.raises(RuntimeError, match="没有注册任何"):
            registry.benchmark(np.zeros((100, 100, 3), dtype=np.uint8))

    def test_benchmark_returns_fastest(self):
        """验证 benchmark 返回最快的引擎名"""
        registry = OCREngineRegistry()
        fast = MockEngine()
        slow = MockEngine()

        registry.register(fast, "fast")
        registry.register(slow, "slow")

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        best_name = registry.benchmark(image)
        assert isinstance(best_name, str)

    def test_benchmark_cache(self):
        """验证 benchmark 结果缓存：重复调用返回相同结果"""
        registry = OCREngineRegistry()
        engine = MockEngine(results=[OCRResult(text="cached", confidence=0.9, box=(0, 0, 10, 10))])
        registry.register(engine, "test")

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        first = registry.benchmark(image)
        second = registry.benchmark(image)
        assert first == second

    def test_get_best_before_benchmark_raises(self):
        """验证 benchmark 前调用 get_best 抛出异常"""
        registry = OCREngineRegistry()
        engine = MockEngine()
        registry.register(engine, "test")
        with pytest.raises(RuntimeError, match="尚未执行基准测试"):
            registry.get_best()

    def test_get_best_after_benchmark(self):
        """验证 benchmark 后可获取最优引擎"""
        registry = OCREngineRegistry()
        engine = MockEngine()
        registry.register(engine, "test")

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        registry.benchmark(image)
        best = registry.get_best()
        assert isinstance(best, BaseOCREngine)
        assert best is engine

    def test_get_engine_by_name(self):
        """验证按名称获取引擎"""
        registry = OCREngineRegistry()
        engine = MockEngine()
        registry.register(engine, "my_engine")
        assert registry.get_engine("my_engine") is engine

    def test_get_engine_not_found_raises(self):
        """验证获取不存在的引擎抛出 KeyError"""
        registry = OCREngineRegistry()
        with pytest.raises(KeyError):
            registry.get_engine("nonexistent")

    def test_reset_cache(self):
        """验证 reset 清除基准测试缓存"""
        registry = OCREngineRegistry()
        engine = MockEngine()
        registry.register(engine, "test")

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        registry.benchmark(image)
        assert registry._benchmarked is True

        registry.reset()
        assert registry._benchmarked is False
        assert registry._best_engine_name is None

    def test_register_resets_benchmark(self):
        """验证新注册引擎会重置基准测试缓存"""
        registry = OCREngineRegistry()
        engine1 = MockEngine()
        registry.register(engine1, "e1")

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        registry.benchmark(image)

        engine2 = MockEngine()
        registry.register(engine2, "e2")
        assert registry._benchmarked is False


class TestOCRResultCache:
    """OCRResultCache 缓存测试"""

    @pytest.fixture
    def sample_results(self):
        """采样 OCR 结果"""
        return [
            OCRResult(text="文本A", confidence=0.95, box=(0, 0, 10, 10)),
            OCRResult(text="文本B", confidence=0.88, box=(10, 10, 20, 20)),
        ]

    def test_compute_hash_deterministic(self):
        """验证同一图像哈希值稳定"""
        image = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        h1 = OCRResultCache.compute_image_hash(image)
        h2 = OCRResultCache.compute_image_hash(image)
        assert h1 == h2

    def test_compute_hash_different_images(self):
        """验证不同图像产生不同哈希"""
        img1 = np.zeros((64, 64, 3), dtype=np.uint8)
        img2 = np.ones((64, 64, 3), dtype=np.uint8) * 255
        h1 = OCRResultCache.compute_image_hash(img1)
        h2 = OCRResultCache.compute_image_hash(img2)
        assert h1 != h2

    def test_get_miss(self, sample_results):
        """验证缓存未命中返回 None"""
        cache = OCRResultCache()
        result = cache.get("nonexistent_hash")
        assert result is None

    def test_set_and_get(self, sample_results):
        """验证缓存写入和读取"""
        cache = OCRResultCache()
        cache.set("hash_abc", sample_results)
        result = cache.get("hash_abc")
        assert result == sample_results

    def test_lru_eviction(self, sample_results):
        """验证 LRU 淘汰：超过 max_size 时淘汰最旧条目"""
        cache = OCRResultCache(max_size=3)

        cache.set("hash_1", sample_results)
        cache.set("hash_2", sample_results)
        cache.set("hash_3", sample_results)
        cache.set("hash_4", sample_results)

        assert cache.get("hash_1") is None
        assert cache.get("hash_4") is not None

    def test_get_moves_to_end(self, sample_results):
        """验证 get 操作将条目移到 LRU 末尾"""
        cache = OCRResultCache(max_size=3)

        cache.set("hash_1", sample_results)
        cache.set("hash_2", sample_results)
        cache.set("hash_3", sample_results)
        cache.get("hash_1")

        cache.set("hash_4", sample_results)
        assert cache.get("hash_1") is not None
        assert cache.get("hash_2") is None

    def test_clear(self, sample_results):
        """验证清空缓存"""
        cache = OCRResultCache()
        cache.set("hash_a", sample_results)
        cache.set("hash_b", sample_results)
        assert cache.size == 2

        cache.clear()
        assert cache.size == 0
        assert cache.get("hash_a") is None

    def test_size_property(self, sample_results):
        """验证 size 属性正确反映缓存条目数"""
        cache = OCRResultCache()
        assert cache.size == 0
        cache.set("h1", sample_results)
        assert cache.size == 1
        cache.set("h2", sample_results)
        assert cache.size == 2

    def test_default_max_size(self):
        """验证默认最大缓存条目数"""
        cache = OCRResultCache()
        assert cache._max_size == 500


class TestOCRNode:
    """OCRNode Pipeline 节点测试（使用 engine OCRNode）"""

    def test_create_node_defaults(self):
        """验证创建节点默认值"""
        node = OCRNode(id="ocr1", name="OCR识别")
        assert node.id == "ocr1"
        assert node.name == "OCR识别"
        assert node.node_type == "ocr"
        assert node.config == {}

    def test_create_node_with_config(self):
        """验证带配置的节点创建"""
        node = OCRNode(
            id="ocr2",
            name="区域识别",
            config={"region": {"x": 10, "y": 20, "w": 100, "h": 50}, "lang": "en"},
        )
        assert node.config["region"] == {"x": 10, "y": 20, "w": 100, "h": 50}
        assert node.config["lang"] == "en"

    def test_create_node_with_expected_text(self):
        """验证带期望文本的节点创建"""
        node = OCRNode(
            id="ocr3",
            name="验证识别",
            config={"expected_text": "确认"},
        )
        assert node.config["expected_text"] == "确认"

    def test_create_node_with_engine_preference(self):
        """验证带引擎偏好的节点创建"""
        node = OCRNode(
            id="ocr4",
            name="引擎偏好",
            config={"engine": "rapid"},
        )
        assert node.config["engine"] == "rapid"

    def test_to_dict(self):
        """验证 PipelineNode 序列化"""
        node = OCRNode(
            id="ocr5",
            name="序列化测试",
            config={"region": {"x": 5, "y": 5, "w": 50, "h": 50}, "lang": "en"},
        )
        d = node.to_dict()
        assert d["id"] == "ocr5"
        assert d["name"] == "序列化测试"
        assert d["node_type"] == "ocr"
        assert d["config"]["lang"] == "en"

    def test_from_dict(self):
        """验证 PipelineNode 反序列化"""
        data = {
            "id": "ocr6",
            "name": "反序列化",
            "node_type": "ocr",
            "config": {
                "region": {"x": 10, "y": 10, "w": 60, "h": 30},
                "expected_text": "确定",
                "lang": "en",
                "engine": "paddle",
            },
        }
        node = OCRNode.from_dict(data)
        assert node.id == "ocr6"
        assert node.name == "反序列化"
        assert node.node_type == "ocr"
        assert node.config["region"] == {"x": 10, "y": 10, "w": 60, "h": 30}
        assert node.config["expected_text"] == "确定"
        assert node.config["engine"] == "paddle"

    def test_round_trip(self):
        """验证序列化/反序列化往返一致性"""
        original = OCRNode(
            id="ocr7",
            name="往返测试",
            config={
                "region": {"x": 1, "y": 2, "w": 3, "h": 4},
                "expected_text": "往返测试",
                "lang": "ch",
                "engine": "rapid",
            },
        )
        restored = OCRNode.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.node_type == original.node_type
        assert restored.config == original.config


class TestOCRNodeGetImageFallback:
    """OCRNode._get_image 截图获取策略测试。

    OCR 节点 _get_image 必须在 context 无 image 时 fallback 到
    device.capture_screen()，与 template_match/feature_match/color_detect
    节点的截图策略对齐。否则在无前置 ScreenshotNode 的 pipeline 中
    （如 BD2 daily_missions）首个 OCR 节点会 fail with
    'No image available (context empty + device capture failed/unavailable)'。

    重现日志：worker/debug/YYYYMMDD/agent/<pipeline>/HH/structured.jsonl
    """

    @pytest.fixture
    def mock_context(self):
        """Build a mock PipelineContext with variables dict."""
        ctx = MagicMock()
        ctx.variables = {}
        ctx.device = None
        ctx.coord_transformer = None
        ctx.debug_mode = False

        def set_var(key, value):
            ctx.variables[key] = value

        def get_var(key, default=None):
            return ctx.variables.get(key, default)

        ctx.set_variable.side_effect = set_var
        ctx.get_variable.side_effect = get_var
        return ctx

    def _make_node(self):
        return OCRNode(id="ocr_test", name="ocr_test")

    def test_fallback_to_device_when_context_empty(self, mock_context):
        """context 无 image 时，应调用 device.capture_screen() 返回截图。"""
        node = self._make_node()
        mock_context.device = MagicMock()
        expected_image = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_context.device.capture_screen.return_value = expected_image

        result = node._get_image(mock_context)

        assert result is expected_image
        mock_context.device.capture_screen.assert_called_once()

    def test_prefers_context_image_over_device(self, mock_context):
        """context 有 'image' 变量时，不应调用 device.capture_screen()。"""
        node = self._make_node()
        ctx_image = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_context.set_variable("image", ctx_image)
        mock_context.device = MagicMock()
        mock_context.device.capture_screen.return_value = np.zeros((50, 50, 3))

        result = node._get_image(mock_context)

        assert result is ctx_image
        mock_context.device.capture_screen.assert_not_called()

    def test_prefers_context_screenshot_variable(self, mock_context):
        """context 有 'screenshot' 变量时也应优先使用，不调用 device。"""
        node = self._make_node()
        ctx_image = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_context.set_variable("screenshot", ctx_image)
        mock_context.device = MagicMock()

        result = node._get_image(mock_context)

        assert result is ctx_image
        mock_context.device.capture_screen.assert_not_called()

    def test_returns_none_when_no_device_no_context(self, mock_context):
        """context 无 image 且无 device 时，返回 None。"""
        node = self._make_node()
        mock_context.device = None

        result = node._get_image(mock_context)

        assert result is None

    def test_returns_none_when_device_capture_raises(self, mock_context):
        """device.capture_screen() 抛异常时，返回 None（不向上抛）。"""
        node = self._make_node()
        mock_context.device = MagicMock()
        mock_context.device.capture_screen.side_effect = RuntimeError("device gone")

        result = node._get_image(mock_context)

        assert result is None

    def test_returns_none_when_device_returns_none(self, mock_context):
        """device.capture_screen() 返回 None 时，返回 None。"""
        node = self._make_node()
        mock_context.device = MagicMock()
        mock_context.device.capture_screen.return_value = None

        result = node._get_image(mock_context)

        assert result is None


class TestOCRNodeLegacyROIOffset:
    """OCRNode legacy 路径 (无 coord_transformer) ROI 偏移回归测试。

    N191 (spec-2026-07-27-execution-path-unification 数据流检查):
    修复前,当 OCR 节点配置了 region 但 PipelineContext.coord_transformer
    为 None (legacy raw-pixel 路径) 时, _crop_region 把图像裁到子图, 但
    publish_match_pos 发布的 box 中心仍是子图内坐标, 没加 region 偏移。
    下游 click 节点拿这个坐标点击会偏移到错误位置 (子图原点是 region.x,
    region.y, 不是 0, 0)。

    本测试模拟: region={x:100, y:50, w:200, h:80}, OCR 检测到 box=[30,40,20,10]
    (子图内坐标), 验证 publish_match_pos 发布的 _last_match_pos 是
    (100+30+10, 50+40+5) = (140, 95) 而非 (40, 45)。
    """

    @pytest.fixture
    def mock_context(self):
        ctx = MagicMock()
        ctx.variables = {}
        ctx.device = None
        ctx.coord_transformer = None
        ctx.debug_mode = False

        def set_var(key, value):
            ctx.variables[key] = value

        def get_var(key, default=None):
            return ctx.variables.get(key, default)

        ctx.set_variable.side_effect = set_var
        ctx.get_variable.side_effect = get_var
        return ctx

    def test_legacy_roi_offset_applied_to_publish_match_pos(self, mock_context):
        """legacy 路径 + region 配置时, publish_match_pos 必须加 region 偏移。"""
        # 构造一个 300x200 全黑图, OCR 在子图 [100,50,200,80] 内检测到
        # box=[30,40,20,10] (相对子图原点)
        full_image = np.zeros((200, 300, 3), dtype=np.uint8)
        mock_context.set_variable("image", full_image)

        node = OCRNode(
            id="ocr_test",
            name="ocr_test",
            config={"region": {"x": 100, "y": 50, "w": 200, "h": 80}},
        )

        # Mock BatchOCRDetector.detect 返回单个 box
        detected_box = [30, 40, 20, 10]
        detected_conf = 0.9
        detected_text = "hello"

        with patch("core.batch_ocr.BatchOCRDetector") as mock_detector_cls:
            mock_detector = mock_detector_cls.return_value
            mock_detector.prepare_batch.return_value = [full_image]
            mock_detector.detect.return_value = [[{
                "text": detected_text,
                "confidence": detected_conf,
                "bbox": detected_box,
            }]]

            with patch.object(node, "_save_debug", return_value={"annotated": None, "raw": None}):
                result = node.execute(mock_context)

        assert result.success, f"OCR execute failed: {result.error_msg}"

        # 验证 _last_match_pos 是全图坐标 (140, 95) 而非子图坐标 (40, 45)
        last_pos = mock_context.variables.get("_last_match_pos")
        assert last_pos is not None, "_last_match_pos 未发布"
        assert last_pos["x"] == 140, (
            f"expected x=140 (region.x=100 + box.x=30 + box.w/2=10), "
            f"got {last_pos['x']}"
        )
        assert last_pos["y"] == 95, (
            f"expected y=95 (region.y=50 + box.y=40 + box.h/2=5), "
            f"got {last_pos['y']}"
        )
        assert last_pos["source"] == "ocr_test:ocr"
        assert last_pos["text"] == detected_text

    def test_legacy_no_region_no_offset(self, mock_context):
        """legacy 路径 + 无 region 时, publish_match_pos 不加偏移 (offset=0,0)。"""
        full_image = np.zeros((200, 300, 3), dtype=np.uint8)
        mock_context.set_variable("image", full_image)

        node = OCRNode(id="ocr_test", name="ocr_test")  # 无 region

        detected_box = [50, 60, 20, 10]
        with patch("core.batch_ocr.BatchOCRDetector") as mock_detector_cls:
            mock_detector = mock_detector_cls.return_value
            mock_detector.prepare_batch.return_value = [full_image]
            mock_detector.detect.return_value = [[{
                "text": "x",
                "confidence": 0.9,
                "bbox": detected_box,
            }]]

            with patch.object(node, "_save_debug", return_value={"annotated": None, "raw": None}):
                result = node.execute(mock_context)

        assert result.success
        last_pos = mock_context.variables.get("_last_match_pos")
        assert last_pos is not None
        # 无 ROI 时, box 直接是全图坐标
        assert last_pos["x"] == 60  # 50 + 20/2
        assert last_pos["y"] == 65  # 60 + 10/2
