"""Local SEO metrics, defined once so every number in a report can be explained.

- Average position (ARP): mean rank across grid points where the business appears.
- Top-3 share (share of local voice): % of grid points where it appears in the top 3,
  which is roughly the Google "map pack" most searchers actually see.
- Visibility score: 0-100. #1 scores 100, each place lower loses 10 points, and #11 or
  lower (or not found) scores 0. Averaged over the grid.
"""
from __future__ import annotations

from dataclasses import dataclass

VISIBLE_POSITIONS = 10


@dataclass(frozen=True)
class GridSummary:
    average_position: float | None
    top3_share: float
    found_share: float
    visibility: float


def visibility_points(position: int | None) -> float:
    if position is None or position > VISIBLE_POSITIONS:
        return 0.0
    return 100.0 - 10.0 * (position - 1)


def summarise(cells: dict[tuple[int, int], int | None]) -> GridSummary:
    if not cells:
        return GridSummary(None, 0.0, 0.0, 0.0)
    positions = list(cells.values())
    found = [p for p in positions if p is not None]
    n = len(positions)
    return GridSummary(
        average_position=round(sum(found) / len(found), 1) if found else None,
        top3_share=round(100 * sum(1 for p in found if p <= 3) / n, 1),
        found_share=round(100 * len(found) / n, 1),
        visibility=round(sum(visibility_points(p) for p in positions) / n, 1),
    )


def change(current: float | None, previous: float | None, lower_is_better: bool = False) -> str:
    """Human-friendly movement label, e.g. '▲ 2.3' (green) or '▼ 1.0' (red)."""
    if current is None or previous is None:
        return ""
    delta = round(current - previous, 1)
    if delta == 0:
        return "–"
    improved = delta < 0 if lower_is_better else delta > 0
    return f"{'▲' if improved else '▼'} {abs(delta):g}"
