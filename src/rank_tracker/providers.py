"""Where rankings come from.

`GoogleProvider` uses the official Google Places API (Text Search, "New" version), which
returns local results in ranked order for a search made from a given point. `DemoProvider`
simulates a realistic local market so the tool can be tried and tested without an API key.
"""
from __future__ import annotations

import hashlib
import math
import os
import random
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class Listing:
    place_id: str
    name: str
    rating: float | None
    reviews: int


class Provider(Protocol):
    def search(self, keyword: str, lat: float, lng: float, on: date) -> list[Listing]:
        """Ranked local results (best first) for `keyword` searched from (lat, lng)."""


class GoogleProvider:
    URL = "https://places.googleapis.com/v1/places:searchText"
    FIELDS = "places.id,places.displayName,places.rating,places.userRatingCount"

    def __init__(self, api_key: str | None = None, radius_m: float = 3000, session=None):
        self.api_key = api_key or os.environ.get("GOOGLE_MAPS_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("Set GOOGLE_MAPS_API_KEY to use the Google provider")
        self.radius_m = radius_m
        if session is None:
            import requests

            session = requests.Session()
        self.session = session

    def search(self, keyword: str, lat: float, lng: float, on: date) -> list[Listing]:
        resp = self.session.post(
            self.URL,
            json={
                "textQuery": keyword,
                "pageSize": 20,
                "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": self.radius_m}},
            },
            headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": self.FIELDS},
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Google Places API error {resp.status_code}: {resp.text[:200]}")
        return [
            Listing(
                place_id=p["id"],
                name=p.get("displayName", {}).get("text", "Unknown"),
                rating=p.get("rating"),
                reviews=int(p.get("userRatingCount", 0)),
            )
            for p in resp.json().get("places", [])
        ]


# ---------------------------------------------------------------- demo market

DEMO_BUSINESSES = [
    # place_id, name, home (lat, lng), base strength, starting rating, starting reviews, reviews per week
    ("demo-brightline", "Brightline Plumbing & Heating", (53.4239, -3.0485), 0.58, 4.6, 30, 3.2),
    ("demo-wirral-flow", "Wirral Flow Plumbing", (53.4060, -3.0300), 0.78, 4.8, 156, 0.6),
    ("demo-pipe-pros", "Pipe Pros Merseyside", (53.4410, -3.0120), 0.70, 4.3, 92, 0.5),
    ("demo-heatwise", "HeatWise Boilers", (53.3990, -3.0700), 0.66, 4.7, 61, 0.8),
    ("demo-coastal", "Coastal Gas & Heating", (53.4350, -3.0800), 0.55, 4.5, 40, 0.4),
    ("demo-ab-plumbing", "A&B Plumbing Services", (53.4150, -3.0050), 0.50, 4.1, 27, 0.2),
    ("demo-quickfix", "QuickFix Drains", (53.4470, -3.0450), 0.45, 3.9, 19, 0.3),
    ("demo-allheat", "AllHeat Engineers", (53.3920, -3.0350), 0.48, 4.4, 33, 0.3),
    ("demo-birk-boilers", "Birkenhead Boiler Co", (53.3930, -3.0150), 0.60, 4.6, 88, 0.5),
    ("demo-hoylake", "Hoylake Plumbing", (53.3900, -3.1800), 0.65, 4.8, 120, 0.4),
    ("demo-moreton", "Moreton Heating Services", (53.4010, -3.1150), 0.55, 4.5, 47, 0.3),
    ("demo-liscard", "Liscard Leak Repairs", (53.4250, -3.0300), 0.40, 4.2, 15, 0.2),
    ("demo-newbrighton", "New Brighton Gas Fitters", (53.4380, -3.0400), 0.52, 4.6, 52, 0.3),
    ("demo-bootle", "Bootle Plumbing & Drains", (53.4460, -2.9950), 0.58, 4.4, 64, 0.4),
    ("demo-prenton", "Prenton Property Maintenance", (53.3800, -3.0450), 0.47, 4.3, 29, 0.2),
    ("demo-seacombe", "Seacombe Pipes & Heat", (53.4100, -3.0200), 0.44, 4.0, 22, 0.1),
]
SEARCH_RADIUS_KM = 6.5  # businesses further than this from the searcher don't appear
DEMO_START = date(2026, 6, 1)


class DemoProvider:
    """A simulated local market. Results depend on distance, reviews, rating, keyword and date.

    The tracked business ("Brightline") steadily gains reviews, so its rankings improve over
    time. That's the kind of story the report is designed to show.
    """

    def search(self, keyword: str, lat: float, lng: float, on: date) -> list[Listing]:
        weeks = max(0, (on - DEMO_START).days / 7)
        scored = []
        for pid, name, (blat, blng), strength, rating, reviews, per_week in DEMO_BUSINESSES:
            total_reviews = int(reviews + per_week * weeks)
            dist_km = math.dist((lat * 111.32, lng * 67.0), (blat * 111.32, blng * 67.0))
            relevance = 0.15 if ("boiler" in keyword and "Boiler" in name) or ("drain" in keyword and "Drain" in name) else 0.0
            score = strength + relevance + 0.13 * math.log1p(total_reviews) + 0.1 * (rating - 4) - 0.11 * dist_km
            seed = int(hashlib.md5(f"{pid}|{keyword}|{lat:.4f}|{lng:.4f}|{on}".encode()).hexdigest()[:8], 16)
            score += random.Random(seed).gauss(0, 0.05)
            if dist_km > SEARCH_RADIUS_KM:
                continue
            scored.append((score, Listing(pid, name, round(min(5.0, rating + 0.002 * weeks * (pid == "demo-brightline")), 1), total_reviews)))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [listing for _, listing in scored]


def get_provider(name: str) -> Provider:
    return GoogleProvider() if name == "google" else DemoProvider()
