"""SQLite history of every check, so trends can be charted over weeks and months."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from .config import GridPoint
from .providers import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    keyword  TEXT NOT NULL,
    UNIQUE (run_date, keyword)
);
CREATE TABLE IF NOT EXISTS results (
    run_id   INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    grid_row INTEGER NOT NULL,
    grid_col INTEGER NOT NULL,
    position INTEGER NOT NULL,
    place_id TEXT NOT NULL,
    name     TEXT NOT NULL,
    rating   REAL,
    reviews  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_place ON results(place_id);
"""


class Store:
    def __init__(self, path: str | Path = "rankings.sqlite"):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def save_run(self, run_date: date, keyword: str, results: dict[GridPoint, list[Listing]], keep: int = 20) -> int:
        """Store one keyword's results across the grid. Re-running the same day replaces them."""
        with self.db:
            self.db.execute("DELETE FROM runs WHERE run_date = ? AND keyword = ?", (run_date.isoformat(), keyword))
            run_id = self.db.execute("INSERT INTO runs (run_date, keyword) VALUES (?, ?)", (run_date.isoformat(), keyword)).lastrowid
            self.db.executemany(
                "INSERT INTO results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (run_id, pt.row, pt.col, pos, l.place_id, l.name, l.rating, l.reviews)
                    for pt, listings in results.items()
                    for pos, l in enumerate(listings[:keep], start=1)
                ],
            )
        return run_id

    def dates(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT run_date FROM runs ORDER BY run_date")]

    def keywords(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT keyword FROM runs ORDER BY keyword")]

    def grid(self, run_date: str, keyword: str, place_id: str) -> dict[tuple[int, int], int | None]:
        """Position of `place_id` at each grid point (None = not in the results)."""
        cells = {
            (r["grid_row"], r["grid_col"]): None
            for r in self.db.execute(
                "SELECT DISTINCT grid_row, grid_col FROM results JOIN runs ON runs.id = run_id WHERE run_date = ? AND keyword = ?",
                (run_date, keyword),
            )
        }
        for r in self.db.execute(
            "SELECT grid_row, grid_col, position FROM results JOIN runs ON runs.id = run_id "
            "WHERE run_date = ? AND keyword = ? AND place_id = ?",
            (run_date, keyword, place_id),
        ):
            cells[(r["grid_row"], r["grid_col"])] = r["position"]
        return cells

    def competitors(self, run_date: str, top: int = 3) -> list[tuple[str, str]]:
        """Businesses that appeared in the top `top` most often on a date: (place_id, name)."""
        rows = self.db.execute(
            "SELECT place_id, name, COUNT(*) n FROM results JOIN runs ON runs.id = run_id "
            "WHERE run_date = ? AND position <= ? GROUP BY place_id, name ORDER BY n DESC",
            (run_date, top),
        )
        return [(r["place_id"], r["name"]) for r in rows]

    def profile(self, run_date: str, place_id: str) -> tuple[str, float | None, int] | None:
        r = self.db.execute(
            "SELECT name, rating, MAX(reviews) reviews FROM results JOIN runs ON runs.id = run_id WHERE run_date = ? AND place_id = ?",
            (run_date, place_id),
        ).fetchone()
        return (r["name"], r["rating"], r["reviews"]) if r and r["name"] else None

    def close(self) -> None:
        with closing(self.db):
            pass
