"""Screenshot comparison: pixel-level diffing and similarity scoring.

Provides :class:`ScreenshotComparator` which compares *actual* screenshots
against *reference* baselines.  The comparison cascade is:

1. **Pillow + numpy** -- structural similarity via mean-squared error when
   both libraries are available (fast and accurate).
2. **Pillow only** -- per-pixel histogram correlation as a lighter fallback.
3. **Raw bytes** -- file-size ratio heuristic when no image libraries are
   installed at all.

Each comparison produces a :class:`ComparisonResult` consumed by the
:mod:`src.tester.results` aggregator.
"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Optional

from rich.console import Console

from .results import ComparisonResult

console = Console()

# ---------------------------------------------------------------------------
# Optional heavy imports
# ---------------------------------------------------------------------------

try:
    from PIL import Image  # type: ignore[import-untyped]

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    import numpy as np  # type: ignore[import-untyped]

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Pure-math helpers (no external deps)
# ---------------------------------------------------------------------------

def _file_size_similarity(a: Path, b: Path) -> float:
    """Crude similarity based on file sizes (0.0-1.0).

    Useful only as a last-resort sanity check -- it cannot detect visual
    differences, but a wildly different file size strongly suggests the
    images are not the same.
    """
    size_a = a.stat().st_size
    size_b = b.stat().st_size
    if size_a == 0 and size_b == 0:
        return 1.0
    if size_a == 0 or size_b == 0:
        return 0.0
    ratio = min(size_a, size_b) / max(size_a, size_b)
    return ratio


# ---------------------------------------------------------------------------
# Pillow-based helpers
# ---------------------------------------------------------------------------

def _pillow_pixel_similarity(actual: Path, reference: Path) -> float:
    """Compute per-pixel similarity using Pillow.

    Both images are normalised to the same size and converted to RGB.
    Similarity is ``1 - (mean absolute difference / 255)``.
    """
    img_a = Image.open(actual).convert("RGB")
    img_b = Image.open(reference).convert("RGB")

    # Resize to common dimensions (use the reference as the target)
    if img_a.size != img_b.size:
        img_a = img_a.resize(img_b.size, Image.LANCZOS)

    if _HAS_NUMPY:
        arr_a = np.asarray(img_a, dtype=np.float64)
        arr_b = np.asarray(img_b, dtype=np.float64)
        mean_abs_diff = float(np.mean(np.abs(arr_a - arr_b)))
        similarity = 1.0 - (mean_abs_diff / 255.0)
        return max(0.0, min(1.0, similarity))

    # Fallback: histogram correlation (much cheaper than iterating pixels)
    hist_a = img_a.histogram()
    hist_b = img_b.histogram()
    return _histogram_correlation(hist_a, hist_b)


def _histogram_correlation(ha: list[int], hb: list[int]) -> float:
    """Pearson correlation coefficient between two image histograms."""
    n = len(ha)
    mean_a = sum(ha) / n
    mean_b = sum(hb) / n
    num = sum((ha[i] - mean_a) * (hb[i] - mean_b) for i in range(n))
    den_a = math.sqrt(sum((ha[i] - mean_a) ** 2 for i in range(n)))
    den_b = math.sqrt(sum((hb[i] - mean_b) ** 2 for i in range(n)))
    if den_a == 0 or den_b == 0:
        return 0.0
    correlation = num / (den_a * den_b)
    # Map from [-1,1] -> [0,1]
    return max(0.0, min(1.0, (correlation + 1.0) / 2.0))


def _generate_diff_image(actual: Path, reference: Path, output: Path) -> Optional[Path]:
    """Create a visual diff image highlighting pixel differences.

    Returns the output path if successful, else ``None``.
    """
    if not (_HAS_PIL and _HAS_NUMPY):
        return None

    try:
        img_a = Image.open(actual).convert("RGB")
        img_b = Image.open(reference).convert("RGB")

        if img_a.size != img_b.size:
            img_a = img_a.resize(img_b.size, Image.LANCZOS)

        arr_a = np.asarray(img_a, dtype=np.float64)
        arr_b = np.asarray(img_b, dtype=np.float64)

        # Absolute diff, amplified for visibility
        diff = np.abs(arr_a - arr_b)
        amplified = np.clip(diff * 5.0, 0, 255).astype(np.uint8)

        diff_img = Image.fromarray(amplified, mode="RGB")
        output.parent.mkdir(parents=True, exist_ok=True)
        diff_img.save(str(output))
        return output
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ScreenshotComparator
# ---------------------------------------------------------------------------

class ScreenshotComparator:
    """Compare actual screenshots against reference baselines.

    Parameters
    ----------
    threshold:
        Default similarity threshold for a comparison to pass (0.0-1.0).
    generate_diffs:
        Whether to produce visual diff images for failing comparisons.
    diff_dir:
        Directory in which to store diff images.  Defaults to a ``diffs/``
        subdirectory next to the actual screenshots.
    """

    def __init__(
        self,
        threshold: float = 0.95,
        *,
        generate_diffs: bool = True,
        diff_dir: Optional[Path] = None,
    ) -> None:
        self.threshold = threshold
        self.generate_diffs = generate_diffs
        self.diff_dir = Path(diff_dir) if diff_dir else None

    # -- Public API ----------------------------------------------------------

    async def compare(
        self,
        actual: Path,
        reference: Path,
        *,
        threshold: Optional[float] = None,
        route: str = "",
        viewport: str = "",
    ) -> ComparisonResult:
        """Compare a single actual screenshot against its reference.

        The comparison is delegated to a thread-pool executor so that
        CPU-intensive image processing does not block the event loop.
        """
        actual = Path(actual)
        reference = Path(reference)
        effective_threshold = threshold if threshold is not None else self.threshold

        # Validate paths
        if not actual.exists():
            return ComparisonResult(
                route=route,
                viewport=viewport,
                similarity=0.0,
                passed=False,
                threshold=effective_threshold,
                actual_path=str(actual),
                reference_path=str(reference),
                issues=[f"Actual screenshot not found: {actual}"],
            )

        if not reference.exists():
            return ComparisonResult(
                route=route,
                viewport=viewport,
                similarity=0.0,
                passed=False,
                threshold=effective_threshold,
                actual_path=str(actual),
                reference_path=str(reference),
                issues=[f"Reference screenshot not found: {reference}"],
            )

        # Run the (potentially expensive) comparison off the event loop
        loop = asyncio.get_running_loop()
        similarity = await loop.run_in_executor(
            None, self._compute_similarity, actual, reference
        )
        passed = similarity >= effective_threshold

        diff_path: Optional[str] = None
        issues: list[str] = []

        if not passed:
            issues.append(
                f"Similarity {similarity:.4f} is below threshold {effective_threshold:.4f}"
            )
            if self.generate_diffs:
                diff_out = self._diff_output_path(actual, route, viewport)
                result_path = await loop.run_in_executor(
                    None, _generate_diff_image, actual, reference, diff_out
                )
                if result_path is not None:
                    diff_path = str(result_path)

        return ComparisonResult(
            route=route,
            viewport=viewport,
            similarity=round(similarity, 6),
            passed=passed,
            threshold=effective_threshold,
            actual_path=str(actual),
            reference_path=str(reference),
            diff_path=diff_path,
            issues=issues,
        )

    async def compare_all(
        self,
        actual_dir: Path,
        reference_dir: Path,
        *,
        threshold: Optional[float] = None,
    ) -> list[ComparisonResult]:
        """Compare every PNG in *actual_dir* against its counterpart in
        *reference_dir*.

        The directory structure under both roots must match.  For each file
        in *actual_dir* the corresponding reference is resolved by
        substituting the base path.
        """
        actual_dir = Path(actual_dir)
        reference_dir = Path(reference_dir)
        results: list[ComparisonResult] = []

        if not actual_dir.exists():
            console.print(f"[red]Actual directory does not exist: {actual_dir}[/red]")
            return results

        actual_files = sorted(actual_dir.rglob("*.png"))
        if not actual_files:
            console.print(f"[yellow]No PNG files found in {actual_dir}[/yellow]")
            return results

        tasks: list[asyncio.Task[ComparisonResult]] = []
        for actual_file in actual_files:
            relative = actual_file.relative_to(actual_dir)
            reference_file = reference_dir / relative

            # Derive route and viewport from the directory structure
            parts = relative.parts
            route = "/".join(parts[:-1]) if len(parts) > 1 else "/"
            viewport = actual_file.stem  # e.g. "desktop" or "mobile"

            tasks.append(
                asyncio.create_task(
                    self.compare(
                        actual_file,
                        reference_file,
                        threshold=threshold,
                        route=route,
                        viewport=viewport,
                    )
                )
            )

        for coro in asyncio.as_completed(tasks):
            results.append(await coro)

        passed_count = sum(1 for r in results if r.passed)
        console.print(
            f"[{'green' if passed_count == len(results) else 'yellow'}]"
            f"Comparisons: {passed_count}/{len(results)} passed[/]"
        )
        return results

    # -- Internal ------------------------------------------------------------

    def _compute_similarity(self, actual: Path, reference: Path) -> float:
        """Synchronous similarity computation (called inside executor)."""
        if _HAS_PIL:
            try:
                return _pillow_pixel_similarity(actual, reference)
            except Exception as exc:
                console.print(f"[yellow]Pillow comparison failed ({exc}), using file-size fallback[/yellow]")

        return _file_size_similarity(actual, reference)

    def _diff_output_path(self, actual: Path, route: str, viewport: str) -> Path:
        """Determine where to write the diff image."""
        if self.diff_dir:
            base = self.diff_dir
        else:
            base = actual.parent.parent / "diffs"
        slug = route.strip("/").replace("/", "-") or "root"
        return base / f"{slug}_{viewport}_diff.png"
