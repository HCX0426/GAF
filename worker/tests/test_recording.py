"""Tests for WindowsEventCapture and RecordingEngine integration.

These tests verify the event capture logic without requiring actual
pynput listeners (which need a real display server). We mock the
pynput listeners and mss screenshot to test the capture logic.
"""

from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Skip all tests on non-Windows to avoid pynput import issues
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="WindowsEventCapture requires Windows pynput listeners",
)


class TestRecordingEngineCapture:
    """Test RecordingEngine.start_capture / stop_capture integration."""

    def test_start_capture_without_start_warns(self, caplog):
        """start_capture() before start() should warn and return."""
        from core.recording import RecordingEngine

        engine = RecordingEngine(screenshot_dir=tempfile.mkdtemp())
        with caplog.at_level("WARNING"):
            engine.start_capture(capture_screenshots=False)
        assert any("before start()" in r.getMessage() for r in caplog.records)
        assert engine._capture is None

    def test_stop_capture_when_not_running(self):
        """stop_capture() when not running should be a no-op."""
        from core.recording import RecordingEngine

        engine = RecordingEngine(screenshot_dir=tempfile.mkdtemp())
        engine.stop_capture()  # Should not raise

    def test_stop_calls_stop_capture(self):
        """stop() should automatically stop capture."""
        from core.recording import RecordingEngine

        engine = RecordingEngine(screenshot_dir=tempfile.mkdtemp())
        engine.start(name="test")
        mock_capture = MagicMock()
        engine._capture = mock_capture
        engine.stop()
        mock_capture.stop.assert_called_once()

    @patch("platforms.windows.event_capture.keyboard")
    @patch("platforms.windows.event_capture.mouse")
    def test_start_capture_creates_listeners(self, mock_mouse, mock_keyboard):
        """start_capture() should create keyboard and mouse listeners."""
        from core.recording import RecordingEngine

        engine = RecordingEngine(screenshot_dir=tempfile.mkdtemp())
        engine.start(name="test")
        engine.start_capture(capture_screenshots=False)

        # Verify listeners were created and started
        mock_keyboard.Listener.assert_called_once()
        mock_mouse.Listener.assert_called_once()
        engine.stop()

    @patch("platforms.windows.event_capture.keyboard")
    @patch("platforms.windows.event_capture.mouse")
    def test_stop_capture_stops_listeners(self, mock_mouse, mock_keyboard):
        """stop_capture() should stop all listeners."""
        from core.recording import RecordingEngine

        engine = RecordingEngine(screenshot_dir=tempfile.mkdtemp())
        engine.start(name="test")
        engine.start_capture(capture_screenshots=False)

        mock_kb_listener = mock_keyboard.Listener.return_value
        mock_mouse_listener = mock_mouse.Listener.return_value

        engine.stop_capture()
        mock_kb_listener.stop.assert_called_once()
        mock_mouse_listener.stop.assert_called_once()


class TestWindowsEventCapture:
    """Test WindowsEventCapture event handling logic."""

    def _make_capture(self):
        """Create a WindowsEventCapture with mocked engine."""
        # Import inside method to avoid mss import at module level
        from platforms.windows.event_capture import WindowsEventCapture

        engine = MagicMock()
        capture = WindowsEventCapture(
            recording_engine=engine,
            capture_screenshots=False,
        )
        return capture, engine

    def test_on_key_press_regular_key(self):
        """Regular key press should call record_key with char."""
        from pynput.keyboard import KeyCode

        capture, engine = self._make_capture()
        capture._running = True
        capture._on_key_press(KeyCode(char="a"))
        engine.record_key.assert_called_once_with("a")

    def test_on_key_press_special_key(self):
        """Special key press should call record_key with key name."""
        from pynput.keyboard import Key

        capture, engine = self._make_capture()
        capture._running = True
        capture._on_key_press(Key.enter)
        engine.record_key.assert_called_once_with("enter")

    def test_on_key_press_not_running(self):
        """When not running, key press should be ignored."""
        from pynput.keyboard import KeyCode

        capture, engine = self._make_capture()
        capture._running = False
        capture._on_key_press(KeyCode(char="a"))
        engine.record_key.assert_not_called()

    def test_on_mouse_click_press(self):
        """Mouse click press should call record_click."""
        from pynput.mouse import Button

        capture, engine = self._make_capture()
        capture._running = True
        capture._on_mouse_click(100, 200, Button.left, True)
        engine.record_click.assert_called_once_with(100, 200, "left")

    def test_on_mouse_click_release_ignored(self):
        """Mouse click release should be ignored (only press recorded)."""
        from pynput.mouse import Button

        capture, engine = self._make_capture()
        capture._running = True
        capture._on_mouse_click(100, 200, Button.left, False)
        engine.record_click.assert_not_called()

    def test_on_mouse_click_dedup(self):
        """Rapid clicks within dedup window should be deduplicated."""
        from pynput.mouse import Button

        capture, engine = self._make_capture()
        capture._running = True
        capture._on_mouse_click(100, 200, Button.left, True)
        capture._on_mouse_click(100, 200, Button.left, True)  # Within 50ms
        engine.record_click.assert_called_once()

    def test_on_mouse_click_right_button(self):
        """Right button click should map to 'right'."""
        from pynput.mouse import Button

        capture, engine = self._make_capture()
        capture._running = True
        capture._on_mouse_click(50, 60, Button.right, True)
        engine.record_click.assert_called_once_with(50, 60, "right")

    def test_on_mouse_click_middle_button(self):
        """Middle button click should map to 'middle'."""
        from pynput.mouse import Button

        capture, engine = self._make_capture()
        capture._running = True
        capture._on_mouse_click(50, 60, Button.middle, True)
        engine.record_click.assert_called_once_with(50, 60, "middle")

    def test_on_mouse_click_not_running(self):
        """When not running, mouse click should be ignored."""
        from pynput.mouse import Button

        capture, engine = self._make_capture()
        capture._running = False
        capture._on_mouse_click(100, 200, Button.left, True)
        engine.record_click.assert_not_called()


class TestRecordingEngineSerialization:
    """Test RecordingEngine save/load round-trip."""

    def test_save_load_roundtrip(self):
        """Save and load should preserve all data."""
        from core.recording import RecordingEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = RecordingEngine(screenshot_dir=tmpdir)
            engine.start(name="roundtrip_test")
            engine.record_click(100, 200, "left")
            engine.record_key("enter")
            engine.record_wait(1.5)

            filepath = os.path.join(tmpdir, "test.gafrecord")
            engine.save(filepath)
            engine.stop()

            loaded = RecordingEngine.load(filepath)
            assert loaded.name == "roundtrip_test"
            assert len(loaded.events) == 3
            assert loaded.events[0].event_type == "click"
            assert loaded.events[0].x == 100
            assert loaded.events[0].y == 200
            assert loaded.events[1].event_type == "key"
            assert loaded.events[1].key == "enter"
            assert loaded.events[2].event_type == "wait"
            assert loaded.events[2].duration == 1.5

    def test_recording_data_to_dict_from_dict(self):
        """RecordingData.to_dict / from_dict should round-trip."""
        from core.recording import ActionEvent, RecordingData

        data = RecordingData(
            id="rec_test",
            name="test",
            created_at="2026-06-24T10:00:00",
            duration=5.0,
            resolution=(1920, 1080),
            events=[
                ActionEvent(event_type="click", x=10, y=20, button="left", timestamp=1.0),
                ActionEvent(event_type="key", key="space", timestamp=2.0),
            ],
        )

        d = data.to_dict()
        assert d["id"] == "rec_test"
        assert d["resolution"] == [1920, 1080]
        assert len(d["events"]) == 2

        loaded = RecordingData.from_dict(d)
        assert loaded.id == "rec_test"
        assert loaded.resolution == (1920, 1080)
        assert len(loaded.events) == 2
        assert loaded.events[0].x == 10
        assert loaded.events[1].key == "space"

    def test_save_without_recording(self):
        """save() without active recording should be a no-op."""
        from core.recording import RecordingEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = RecordingEngine(screenshot_dir=tmpdir)
            filepath = os.path.join(tmpdir, "empty.gafrecord")
            engine.save(filepath)  # Should not raise
            assert not os.path.exists(filepath)


class TestRecordingToPipeline:
    """Test recording_to_pipeline converter."""

    def test_convert_click_events(self):
        """Click events should become click nodes."""
        from core.recording import ActionEvent, RecordingData
        from core.recording_to_pipeline import convert_recording_to_pipeline

        data = RecordingData(
            id="rec_test",
            name="test",
            events=[
                ActionEvent(event_type="click", x=100, y=200, button="left", timestamp=1.0),
                ActionEvent(event_type="click", x=300, y=400, button="left", timestamp=2.0),
            ],
        )

        pipeline = convert_recording_to_pipeline(data, pipeline_name="test_pipeline")
        assert pipeline["name"] == "test_pipeline"
        # Should have click nodes + wait nodes (auto-inserted)
        click_nodes = [n for n in pipeline["nodes"] if n.get("node_type") == "click"]
        assert len(click_nodes) >= 2

    def test_convert_key_events(self):
        """Key events should become key_press nodes."""
        from core.recording import ActionEvent, RecordingData
        from core.recording_to_pipeline import convert_recording_to_pipeline

        data = RecordingData(
            id="rec_test",
            name="test",
            events=[
                ActionEvent(event_type="key", key="enter", timestamp=1.0),
                ActionEvent(event_type="key", key="space", timestamp=2.0),
            ],
        )

        pipeline = convert_recording_to_pipeline(data)
        key_nodes = [n for n in pipeline["nodes"] if n.get("node_type") == "key_press"]
        assert len(key_nodes) >= 2

    def test_convert_wait_events(self):
        """Wait events should become wait nodes."""
        from core.recording import ActionEvent, RecordingData
        from core.recording_to_pipeline import convert_recording_to_pipeline

        data = RecordingData(
            id="rec_test",
            name="test",
            events=[
                ActionEvent(event_type="wait", duration=2.0, timestamp=1.0),
            ],
        )

        pipeline = convert_recording_to_pipeline(data)
        wait_nodes = [n for n in pipeline["nodes"] if n.get("node_type") == "wait"]
        assert len(wait_nodes) >= 1

    def test_convert_empty_recording(self):
        """Empty recording should produce empty pipeline."""
        from core.recording import RecordingData
        from core.recording_to_pipeline import convert_recording_to_pipeline

        data = RecordingData(id="rec_empty", name="empty", events=[])
        pipeline = convert_recording_to_pipeline(data)
        assert len(pipeline["nodes"]) == 0

    def test_merge_nearby_clicks(self):
        """Nearby clicks (same position, <1s) should be merged."""
        from core.recording import ActionEvent, RecordingData
        from core.recording_to_pipeline import convert_recording_to_pipeline

        data = RecordingData(
            id="rec_test",
            name="test",
            events=[
                ActionEvent(event_type="click", x=100, y=200, button="left", timestamp=1.0),
                ActionEvent(event_type="click", x=101, y=201, button="left", timestamp=1.5),  # <1s, <5px
                ActionEvent(event_type="click", x=500, y=500, button="left", timestamp=3.0),  # Different
            ],
        )

        pipeline = convert_recording_to_pipeline(data)
        click_nodes = [n for n in pipeline["nodes"] if n.get("node_type") == "click"]
        # 2 clicks after merge (first two merged)
        assert len(click_nodes) == 2
