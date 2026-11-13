"""Load and validate the tracker's TOML config file."""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

EXAMPLE = '''# Local SEO rank tracker config
# Searches to track
keywords = ["plumber", "emergency plumber", "boiler repair", "boiler service"]

# Optional: competitors to watch (place ids). Leave empty to track whoever ranks in the top 3.
competitors = []

[business]
name = "Brightline Plumbing & Heating"
# The Google place id of the business you are tracking (find it with: rank-tracker find "name, town")
place_id = "demo-brightline"

[grid]
# Centre of the area you serve, and how far out to check
lat = 53.4239
lng = -3.0485
radius_km = 5
size = 5            # 5 x 5 = 25 search points

[provider]
name = "demo"       # "demo" (simulated, no key needed) or "google" (needs GOOGLE_MAPS_API_KEY)
'''


@dataclass(frozen=True)
class GridPoint:
    row: int
    col: int
    lat: float
    lng: float


@dataclass
class Config:
    business_name: str
    place_id: str
    lat: float
    lng: float
    radius_km: float
    size: int
    keywords: list[str]
    competitors: list[str] = field(default_factory=list)
    provider: str = "demo"

    def grid(self) -> list[GridPoint]:
        """An odd-sized square grid of search points centred on the business area."""
        if self.size == 1:
            return [GridPoint(0, 0, self.lat, self.lng)]
        step_km = 2 * self.radius_km / (self.size - 1)
        km_per_deg_lat = 111.32
        km_per_deg_lng = 111.32 * math.cos(math.radians(self.lat))
        half = self.size // 2
        points = []
        for r in range(self.size):
            for c in range(self.size):
                dy, dx = (half - r) * step_km, (c - half) * step_km  # row 0 is north
                points.append(GridPoint(r, c, round(self.lat + dy / km_per_deg_lat, 6), round(self.lng + dx / km_per_deg_lng, 6)))
        return points


def load(path: str | Path) -> Config:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    try:
        business, grid = raw["business"], raw["grid"]
        cfg = Config(
            business_name=str(business["name"]),
            place_id=str(business["place_id"]),
            lat=float(grid["lat"]),
            lng=float(grid["lng"]),
            radius_km=float(grid.get("radius_km", 5)),
            size=int(grid.get("size", 5)),
            keywords=[str(k).strip() for k in raw["keywords"] if str(k).strip()],
            competitors=[str(c) for c in raw.get("competitors", [])],
            provider=str(raw.get("provider", {}).get("name", "demo")),
        )
    except KeyError as exc:
        raise ValueError(f"Config is missing required setting: {exc.args[0]}") from None
    if cfg.size < 1 or cfg.size % 2 == 0 or cfg.size > 9:
        raise ValueError("grid.size must be an odd number from 1 to 9")
    if not -90 <= cfg.lat <= 90 or not -180 <= cfg.lng <= 180:
        raise ValueError("grid.lat / grid.lng are out of range")
    if not cfg.keywords:
        raise ValueError("Add at least one keyword")
    if cfg.provider not in ("demo", "google"):
        raise ValueError('provider.name must be "demo" or "google"')
    return cfg
