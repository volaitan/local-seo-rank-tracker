"""Build a single, self-contained HTML report (charts embedded), ready to email to a client."""
from __future__ import annotations

import base64
import io
from datetime import datetime
from importlib.resources import files

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from jinja2 import Environment, select_autoescape  # noqa: E402

from .config import Config  # noqa: E402
from .metrics import change, summarise  # noqa: E402
from .storage import Store  # noqa: E402

PALETTE = ["#2f5fd0", "#e8890c", "#2e9e6a", "#c2417a", "#7a5cc7", "#8a97a8"]
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _cell_colour(pos: int | None) -> str:
    if pos is None:
        return "#d9534f"
    if pos <= 3:
        return "#2e9e6a"
    if pos <= 10:
        return "#e8a90c"
    return "#e06d3c"


def build_context(cfg: Config, store: Store) -> dict:
    dates = store.dates()
    if not dates:
        raise ValueError("No data yet. Run `rank-tracker check` first.")
    latest, previous = dates[-1], (dates[-2] if len(dates) > 1 else None)

    keywords = []
    for kw in store.keywords():
        now = summarise(store.grid(latest, kw, cfg.place_id))
        before = summarise(store.grid(previous, kw, cfg.place_id)) if previous else None
        cells = store.grid(latest, kw, cfg.place_id)
        size = max((r for r, _ in cells), default=0) + 1
        keywords.append({
            "keyword": kw,
            "summary": now,
            "arp_change": change(now.average_position, before.average_position if before else None, lower_is_better=True),
            "top3_change": change(now.top3_share, before.top3_share if before else None),
            "vis_change": change(now.visibility, before.visibility if before else None),
            "grid": [[(cells.get((r, c)), _cell_colour(cells.get((r, c)))) for c in range(size)] for r in range(size)],
        })

    # Visibility trend per keyword
    fig, ax = plt.subplots(figsize=(7.5, 3))
    for i, kw in enumerate(store.keywords()):
        ax.plot(dates, [summarise(store.grid(d, kw, cfg.place_id)).visibility for d in dates],
                marker="o", ms=3, color=PALETTE[i % len(PALETTE)], label=kw)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Visibility (0–100)")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    ax.tick_params(axis="x", rotation=45)
    if len(dates) > 12:
        ax.set_xticks(dates[:: max(1, len(dates) // 10)])
    trend_chart = _png(fig)

    # Competitors: who holds the map pack, with ratings and review counts
    ids = list(dict.fromkeys([cfg.place_id, *cfg.competitors, *(pid for pid, _ in store.competitors(latest))]))[:6]
    competitors = []
    for pid in ids:
        prof = store.profile(latest, pid)
        if not prof:
            continue
        name, rating, reviews = prof
        vis = sum(summarise(store.grid(latest, kw, pid)).visibility for kw in store.keywords()) / max(1, len(store.keywords()))
        competitors.append({"name": name, "rating": rating, "reviews": reviews, "visibility": round(vis, 1), "you": pid == cfg.place_id})
    competitors.sort(key=lambda c: c["visibility"], reverse=True)

    # Review growth vs top competitors
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    for i, pid in enumerate(ids[:4]):
        series = [(d, store.profile(d, pid)) for d in dates]
        pts = [(d, p[2]) for d, p in series if p]
        if pts:
            name = pts and store.profile(latest, pid)[0]
            ax.plot([d for d, _ in pts], [v for _, v in pts], color=PALETTE[i], lw=2.5 if pid == cfg.place_id else 1.2, label=name)
    ax.set_ylabel("Google reviews")
    ax.legend(frameon=False, fontsize=8)
    ax.tick_params(axis="x", rotation=45)
    if len(dates) > 12:
        ax.set_xticks(dates[:: max(1, len(dates) // 10)])
    reviews_chart = _png(fig)

    return {
        "cfg": cfg, "latest": latest, "previous": previous, "keywords": keywords, "competitors": competitors,
        "trend_chart": trend_chart, "reviews_chart": reviews_chart, "checks": len(dates),
        "generated": datetime.now().strftime("%d %b %Y %H:%M"), "actions": suggestions(keywords, competitors),
    }


def suggestions(keywords: list[dict], competitors: list[dict]) -> list[str]:
    tips = []
    you = next((c for c in competitors if c["you"]), None)
    leader = competitors[0] if competitors else None
    if you and leader and not leader["you"] and leader["reviews"] > you["reviews"]:
        gap = leader["reviews"] - you["reviews"]
        tips.append(f"{leader['name']} has {gap} more reviews. Ask every happy customer for a review; it's the strongest lever here.")
    weak = [k["keyword"] for k in keywords if k["summary"].top3_share < 30]
    if weak:
        tips.append("Low map-pack presence for: " + ", ".join(f"“{w}”" for w in weak)
                    + ". Add these services to your Google Business Profile and website.")
    edge = [k["keyword"] for k in keywords if k["summary"].found_share < 100]
    if edge:
        tips.append("You drop out of results at the edges of your area for some searches. Posts and photos tagged with "
                    "those towns, plus local landing pages, can help.")
    return tips or ["Strong position across the board: keep reviews coming in and post updates regularly."]


def render(cfg: Config, store: Store) -> str:
    env = Environment(autoescape=select_autoescape(["html"]))
    template = env.from_string(files("rank_tracker").joinpath("templates/report.html").read_text("utf-8"))
    return template.render(**build_context(cfg, store))
