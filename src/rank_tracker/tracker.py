"""Run a check: search every keyword from every grid point and store the results."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from .config import Config
from .metrics import GridSummary, summarise
from .providers import Provider
from .storage import Store


def run_check(cfg: Config, provider: Provider, store: Store, on: date, workers: int = 4) -> dict[str, GridSummary]:
    points = cfg.grid()
    summaries = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for keyword in cfg.keywords:
            listings = pool.map(lambda pt: provider.search(keyword, pt.lat, pt.lng, on), points)
            store.save_run(on, keyword, dict(zip(points, listings)))
            summaries[keyword] = summarise(store.grid(on.isoformat(), keyword, cfg.place_id))
    return summaries
