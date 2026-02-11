"""Unit tests for screenshot capture (src.tester.screenshot).

Tests cover:
- Viewport dataclass and constants (DESKTOP, MOBILE)
- _slugify helper (route path to safe directory name)
- _build_playwright_script generation
- ScreenshotCapture.__init__ defaults and custom values
- ScreenshotCapture.capture_route (single route, mock subprocess)
- ScreenshotCapture.capture_all_routes (multi-route, multi-viewport)
- Error handling (subprocess failure, missing output file)
- Viewport dimension verification (1440x900, 375x812)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tester.screenshot import (
    DESKTOP,
    DEFAULT_VIEWPORTS,
    MOBILE,
    ScreenshotCapture,
    Viewport,
    _build_playwright_script,
    _slugify,
)


# ---------------------------------------------------------------------------
# Viewport
# ---------------------------------------------------------------------------

class TestViewport:
    @pytest.mark.unit
    def test_desktop_dimensions(self):
        assert DESKTOP.name == "desktop"
        assert DESKTOP.width == 1440
        assert DESKTOP.height == 900

    @pytest.mark.unit
    def test_mobile_dimensions(self):
        assert MOBILE.name == "mobile"
        assert MOBILE.width == 375
        assert MOBILE.height == 812

    @pytest.mark.unit
    def test_frozen_viewport(self):
        with pytest.raises(AttributeError):
            DESKTOP.width = 1920  # type: ignore[misc]

    @pytest.mark.unit
    def test_default_viewports_includes_both(self):
        assert DESKTOP in DEFAULT_VIEWPORTS
        assert MOBILE in DEFAULT_VIEWPORTS
        assert len(DEFAULT_VIEWPORTS) == 2

    @pytest.mark.unit
    def test_custom_viewport(self):
        tablet = Viewport("tablet", 768, 1024)
        assert tablet.name == "tablet"
        assert tablet.width == 768
        assert tablet.height == 1024


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    @pytest.mark.unit
    def test_root_route(self):
        assert _slugify("/") == "root"

    @pytest.mark.unit
    def test_simple_route(self):
        assert _slugify("/tasks") == "tasks"

    @pytest.mark.unit
    def test_nested_route(self):
        assert _slugify("/tasks/123/edit") == "tasks-123-edit"

    @pytest.mark.unit
    def test_trailing_slash(self):
        assert _slugify("/tasks/") == "tasks"

    @pytest.mark.unit
    def test_empty_string(self):
        assert _slugify("") == "root"

    @pytest.mark.unit
    def test_special_characters(self):
        result = _slugify("/api/v1/tasks?query=hello")
        assert result == "api-v1-tasks-query-hello"

    @pytest.mark.unit
    def test_uppercase_lowered(self):
        result = _slugify("/MyRoute")
        assert result == "myroute"


# ---------------------------------------------------------------------------
# _build_playwright_script
# ---------------------------------------------------------------------------

class TestBuildPlaywrightScript:
    @pytest.mark.unit
    def test_contains_url(self):
        script = _build_playwright_script("http://localhost:23000/tasks", DESKTOP, Path("/tmp/ss.png"))
        assert "http://localhost:23000/tasks" in script

    @pytest.mark.unit
    def test_contains_viewport_dimensions(self):
        script = _build_playwright_script("http://x", DESKTOP, Path("/tmp/ss.png"))
        assert "1440" in script
        assert "900" in script

    @pytest.mark.unit
    def test_contains_mobile_dimensions(self):
        script = _build_playwright_script("http://x", MOBILE, Path("/tmp/ss.png"))
        assert "375" in script
        assert "812" in script

    @pytest.mark.unit
    def test_contains_output_path(self):
        script = _build_playwright_script("http://x", DESKTOP, Path("/out/screenshot.png"))
        assert "/out/screenshot.png" in script

    @pytest.mark.unit
    def test_contains_chromium_launch(self):
        script = _build_playwright_script("http://x", DESKTOP, Path("/tmp/ss.png"))
        assert "chromium.launch" in script
        assert "headless: true" in script

    @pytest.mark.unit
    def test_contains_network_idle(self):
        script = _build_playwright_script("http://x", DESKTOP, Path("/tmp/ss.png"))
        assert "networkidle" in script

    @pytest.mark.unit
    def test_contains_full_page(self):
        script = _build_playwright_script("http://x", DESKTOP, Path("/tmp/ss.png"))
        assert "fullPage: true" in script


# ---------------------------------------------------------------------------
# ScreenshotCapture.__init__
# ---------------------------------------------------------------------------

class TestScreenshotCaptureInit:
    @pytest.mark.unit
    def test_defaults(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)
        assert capture.base_url == "http://localhost:23000"
        assert capture.output_dir == tmp_path
        assert len(capture.viewports) == 2
        assert capture.timeout_seconds == 60

    @pytest.mark.unit
    def test_trailing_slash_stripped(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000/", tmp_path)
        assert capture.base_url == "http://localhost:23000"

    @pytest.mark.unit
    def test_custom_viewports(self, tmp_path: Path):
        custom = [Viewport("tablet", 768, 1024)]
        capture = ScreenshotCapture("http://localhost:23000", tmp_path, viewports=custom)
        assert capture.viewports == custom

    @pytest.mark.unit
    def test_custom_timeout(self, tmp_path: Path):
        capture = ScreenshotCapture("http://x", tmp_path, timeout_seconds=30)
        assert capture.timeout_seconds == 30


# ---------------------------------------------------------------------------
# ScreenshotCapture.capture_route
# ---------------------------------------------------------------------------

class TestScreenshotCaptureRoute:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_capture_creates_correct_path(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)

        async def _mock_capture(url, viewport, output):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("fake png")
            return output

        with patch.object(capture, "_run_playwright_capture", side_effect=_mock_capture):
            result = await capture.capture_route("/tasks", DESKTOP)

        assert result == tmp_path / "tasks" / "desktop.png"
        assert result.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_capture_root_route(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)

        async def _mock_capture(url, viewport, output):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("fake png")
            return output

        with patch.object(capture, "_run_playwright_capture", side_effect=_mock_capture):
            result = await capture.capture_route("/", DESKTOP)

        assert result == tmp_path / "root" / "desktop.png"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_capture_builds_correct_url(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)
        captured_urls = []

        async def _mock_capture(url, viewport, output):
            captured_urls.append(url)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("fake png")
            return output

        with patch.object(capture, "_run_playwright_capture", side_effect=_mock_capture):
            await capture.capture_route("/tasks", DESKTOP)

        assert captured_urls == ["http://localhost:23000/tasks"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_capture_subprocess_failure_raises(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Error: chromium not found"))
        mock_proc.returncode = 1

        with patch.object(capture, "_try_npx_screenshot", return_value=None):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch("asyncio.wait_for", return_value=(b"", b"Error: chromium not found")):
                    with pytest.raises(RuntimeError, match="Playwright screenshot failed"):
                        await capture.capture_route("/tasks", DESKTOP)


# ---------------------------------------------------------------------------
# ScreenshotCapture.capture_all_routes
# ---------------------------------------------------------------------------

class TestScreenshotCaptureAllRoutes:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_captures_all_route_viewport_combinations(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)
        captured = []

        async def _mock_capture(route, viewport):
            captured.append((route, viewport.name))
            out = tmp_path / _slugify(route) / f"{viewport.name}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("fake")
            return out

        with patch.object(capture, "capture_route", side_effect=_mock_capture):
            result = await capture.capture_all_routes(["/", "/tasks"])

        assert len(captured) == 4  # 2 routes * 2 viewports
        assert "/" in result
        assert "/tasks" in result
        assert "desktop" in result["/"]
        assert "mobile" in result["/"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_captures_with_custom_viewports(self, tmp_path: Path):
        custom = [Viewport("tablet", 768, 1024)]
        capture = ScreenshotCapture("http://localhost:23000", tmp_path, viewports=custom)
        captured = []

        async def _mock_capture(route, viewport):
            captured.append((route, viewport.name))
            out = tmp_path / _slugify(route) / f"{viewport.name}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("fake")
            return out

        with patch.object(capture, "capture_route", side_effect=_mock_capture):
            result = await capture.capture_all_routes(["/tasks"])

        assert len(captured) == 1  # 1 route * 1 viewport
        assert "tablet" in result["/tasks"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_routes_returns_empty(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)
        result = await capture.capture_all_routes([])
        assert result == {}


# ---------------------------------------------------------------------------
# ScreenshotCapture._try_npx_screenshot
# ---------------------------------------------------------------------------

class TestTryNpxScreenshot:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_npx_success(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)
        output = tmp_path / "ss.png"
        output.write_text("png data")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"OK", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("asyncio.wait_for", return_value=(b"OK", b"")):
                result = await capture._try_npx_screenshot("http://x", DESKTOP, output)

        assert result == output

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_npx_not_found_returns_none(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = await capture._try_npx_screenshot(
                "http://x", DESKTOP, tmp_path / "ss.png"
            )

        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_npx_timeout_returns_none(self, tmp_path: Path):
        capture = ScreenshotCapture("http://localhost:23000", tmp_path)

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.returncode = -1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await capture._try_npx_screenshot(
                    "http://x", DESKTOP, tmp_path / "ss.png"
                )

        assert result is None
