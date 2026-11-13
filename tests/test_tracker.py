from datetime import date

import pytest

from rank_tracker import config, metrics
from rank_tracker.cli import main
from rank_tracker.providers import DemoProvider, GoogleProvider, Listing
from rank_tracker.report import render, suggestions
from rank_tracker.storage import Store
from rank_tracker.tracker import run_check


@pytest.fixture
def cfg_path(tmp_path):
    path = tmp_path / "tracker.toml"
    path.write_text(config.EXAMPLE)
    return path


@pytest.fixture
def cfg(cfg_path):
    return config.load(cfg_path)


# ---------- config ----------

def test_example_config_loads(cfg):
    assert cfg.business_name.startswith("Brightline")
    assert cfg.keywords == ["plumber", "emergency plumber", "boiler repair", "boiler service"]
    assert cfg.size == 5 and cfg.provider == "demo"


def test_grid_is_centred_and_spaced(cfg):
    grid = cfg.grid()
    assert len(grid) == 25
    centre = next(p for p in grid if (p.row, p.col) == (2, 2))
    assert (centre.lat, centre.lng) == (cfg.lat, cfg.lng)
    north = next(p for p in grid if (p.row, p.col) == (0, 2))
    assert north.lat > centre.lat                                   # row 0 is north
    assert abs((north.lat - centre.lat) * 111.32 - cfg.radius_km) < 0.01  # edge is radius_km away


@pytest.mark.parametrize("bad,match", [
    ("size = 5", "size = 4"),
    ('name = "demo"', 'name = "bing"'),
    ("lat = 53.4239", "lat = 123"),
])
def test_config_validation(tmp_path, bad, match):
    path = tmp_path / "bad.toml"
    path.write_text(config.EXAMPLE.replace(bad, match))
    with pytest.raises(ValueError):
        config.load(path)


def test_missing_setting_has_clear_message(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text(config.EXAMPLE.replace('place_id = "demo-brightline"', ""))
    with pytest.raises(ValueError, match="place_id"):
        config.load(path)


# ---------- metrics ----------

def test_visibility_points():
    assert metrics.visibility_points(1) == 100
    assert metrics.visibility_points(4) == 70
    assert metrics.visibility_points(10) == 10
    assert metrics.visibility_points(11) == 0
    assert metrics.visibility_points(None) == 0


def test_summarise():
    s = metrics.summarise({(0, 0): 1, (0, 1): 3, (1, 0): 8, (1, 1): None})
    assert s.average_position == 4.0
    assert s.top3_share == 50.0
    assert s.found_share == 75.0
    assert s.visibility == (100 + 80 + 30 + 0) / 4


def test_change_labels():
    assert metrics.change(4.0, 5.5, lower_is_better=True) == "▲ 1.5"   # position went from 5.5 to 4 = better
    assert metrics.change(40, 50) == "▼ 10"
    assert metrics.change(5, 5) == "–"
    assert metrics.change(5, None) == ""


# ---------- providers ----------

def test_demo_provider_is_deterministic_and_local():
    p = DemoProvider()
    a = p.search("plumber", 53.4239, -3.0485, date(2026, 7, 1))
    assert a == p.search("plumber", 53.4239, -3.0485, date(2026, 7, 1))
    far = p.search("plumber", 53.48, -2.90, date(2026, 7, 1))       # ~12 km away
    assert {l.place_id for l in a} != {l.place_id for l in far}


def test_demo_business_improves_as_reviews_grow():
    p = DemoProvider()
    early = [l.place_id for l in p.search("plumber", 53.4239, -3.0485, date(2026, 6, 1))]
    later = [l.place_id for l in p.search("plumber", 53.4239, -3.0485, date(2027, 6, 1))]
    assert later.index("demo-brightline") <= early.index("demo-brightline")


class FakeResponse:
    status_code = 200

    def json(self):
        return {"places": [
            {"id": "abc", "displayName": {"text": "Top Plumber"}, "rating": 4.9, "userRatingCount": 210},
            {"id": "def", "displayName": {"text": "New Plumber"}},
        ]}


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers))
        return FakeResponse()


def test_google_provider_request_and_parsing():
    session = FakeSession()
    listings = GoogleProvider(api_key="test-key", session=session).search("plumber", 53.4, -3.0, date.today())
    assert listings == [Listing("abc", "Top Plumber", 4.9, 210), Listing("def", "New Plumber", None, 0)]
    url, body, headers = session.calls[0]
    assert body["textQuery"] == "plumber"
    assert body["locationBias"]["circle"]["center"] == {"latitude": 53.4, "longitude": -3.0}
    assert headers["X-Goog-Api-Key"] == "test-key"
    assert "places.userRatingCount" in headers["X-Goog-FieldMask"]


def test_google_provider_needs_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_MAPS_API_KEY"):
        GoogleProvider(session=FakeSession())


# ---------- storage, tracking and report ----------

def test_check_store_and_rerun_same_day(cfg, tmp_path):
    store = Store(tmp_path / "r.sqlite")
    summaries = run_check(cfg, DemoProvider(), store, date(2026, 7, 6))
    assert set(summaries) == set(cfg.keywords)
    run_check(cfg, DemoProvider(), store, date(2026, 7, 6))          # same day again replaces, not duplicates
    assert store.dates() == ["2026-07-06"]
    n = store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    assert n == len(cfg.keywords)
    assert len(store.grid("2026-07-06", "plumber", cfg.place_id)) == 25


def test_report_contains_key_sections(cfg, tmp_path):
    store = Store(tmp_path / "r.sqlite")
    for d in (date(2026, 7, 6), date(2026, 7, 13)):
        run_check(cfg, DemoProvider(), store, d)
    html = render(cfg, store)
    for text in ("Brightline Plumbing", "Where you rank", "Visibility over time", "Competitors", "(you)", "data:image/png;base64"):
        assert text in html
    assert "compared with 2026-07-06" in html


def test_report_needs_data(cfg, tmp_path):
    with pytest.raises(ValueError, match="No data"):
        render(cfg, Store(tmp_path / "empty.sqlite"))


def test_suggestions_point_at_review_gap():
    s = metrics.GridSummary(5.0, 10.0, 80.0, 50.0)
    tips = suggestions(
        [{"keyword": "plumber", "summary": s}],
        [{"name": "Rival", "reviews": 150, "you": False, "visibility": 70}, {"name": "Me", "reviews": 40, "you": True, "visibility": 50}],
    )
    assert "110 more reviews" in tips[0]
    assert any("plumber" in t for t in tips)


def test_cli_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert main(["init"]) == 1                     # won't overwrite
    assert main(["demo", "--weeks", "3"]) == 0
    assert main(["check", "--date", "2026-07-01"]) == 0
    assert main(["report", "--out", "out.html"]) == 0
    assert (tmp_path / "out.html").stat().st_size > 10_000
    assert main(["find", "plumber"]) == 0
    assert "place_id=" in capsys.readouterr().out
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert main(["email", "--to", "client@example.com"]) == 1   # explains missing SMTP settings
