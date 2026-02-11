"""NC Dev System -- Tester module.

Provides test execution, screenshot capture, AI-powered visual analysis,
screenshot comparison, result aggregation, and automated fix-retest loops.

Public API
----------
.. autoclass:: TestRunner
.. autoclass:: ScreenshotCapture
.. autoclass:: VisionAnalyzer
.. autoclass:: ScreenshotComparator
.. autoclass:: FixRetestLoop
.. autoclass:: TestSuiteResults
.. autoclass:: TestResults
.. autoclass:: VisualTestResults
.. autoclass:: VisionResult
.. autoclass:: ComparisonResult
.. autoclass:: TestFailure
"""

from .comparator import ScreenshotComparator
from .fix_loop import FixRetestLoop
from .results import (
    ComparisonResult,
    TestFailure,
    TestResults,
    TestSuiteResults,
    VisionIssue,
    VisionResult,
    VisualTestResults,
)
from .runner import TestRunner
from .screenshot import DESKTOP, MOBILE, ScreenshotCapture, Viewport
from .vision import VisionAnalyzer

__all__ = [
    # Runner
    "TestRunner",
    # Screenshot
    "ScreenshotCapture",
    "Viewport",
    "DESKTOP",
    "MOBILE",
    # Vision
    "VisionAnalyzer",
    "VisionResult",
    "VisionIssue",
    # Comparator
    "ScreenshotComparator",
    "ComparisonResult",
    # Results
    "TestResults",
    "TestFailure",
    "TestSuiteResults",
    "VisualTestResults",
    # Fix loop
    "FixRetestLoop",
]
