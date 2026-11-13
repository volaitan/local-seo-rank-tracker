"""rank-tracker: init | find | check | demo | report | email"""
from __future__ import annotations

import argparse
import os
import smtplib
import sys
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

from . import __version__, config, providers, report
from .storage import Store
from .tracker import run_check


def cmd_init(args) -> int:
    path = Path(args.config)
    if path.exists() and not args.force:
        print(f"{path} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    path.write_text(config.EXAMPLE, encoding="utf-8")
    print(f"Created {path}. Edit it, then run: rank-tracker check")
    return 0


def cmd_find(args) -> int:
    """Look up a business's place id so it can go in the config."""
    cfg = config.load(args.config)
    provider = providers.get_provider(cfg.provider)
    for i, l in enumerate(provider.search(args.query, cfg.lat, cfg.lng, date.today())[:10], 1):
        print(f"{i:>2}. {l.name}  ({l.rating or '—'}★, {l.reviews} reviews)  place_id={l.place_id}")
    return 0


def cmd_check(args) -> int:
    cfg = config.load(args.config)
    on = date.fromisoformat(args.date) if args.date else date.today()
    store = Store(args.db)
    summaries = run_check(cfg, providers.get_provider(cfg.provider), store, on)
    print(f"Checked {len(cfg.keywords)} keywords × {cfg.size * cfg.size} grid points on {on}")
    for kw, s in summaries.items():
        arp = s.average_position if s.average_position is not None else "—"
        print(f"  {kw:<24} visibility {s.visibility:>5}   top-3 {s.top3_share:>5}%   avg position {arp}")
    return 0


def cmd_demo(args) -> int:
    """Fill the database with weekly demo checks so the report has a history to show."""
    cfg = config.load(args.config)
    if cfg.provider != "demo":
        print("demo only works with provider.name = \"demo\"", file=sys.stderr)
        return 1
    store = Store(args.db)
    start = date.fromisoformat(args.start)
    for week in range(args.weeks):
        run_check(cfg, providers.DemoProvider(), store, start + timedelta(weeks=week))
    print(f"Recorded {args.weeks} weekly demo checks from {start}")
    return 0


def cmd_report(args) -> int:
    cfg = config.load(args.config)
    html = report.render(cfg, Store(args.db))
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"Report written to {args.out}")
    return 0


def cmd_email(args) -> int:
    """Email the HTML report. SMTP settings come from environment variables."""
    cfg = config.load(args.config)
    needed = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"]
    missing = [v for v in needed if not os.environ.get(v)]
    if missing:
        print(f"Set {', '.join(missing)} to send email", file=sys.stderr)
        return 1
    msg = EmailMessage()
    msg["Subject"] = f"Weekly local rankings: {cfg.business_name}"
    msg["From"] = os.environ.get("SMTP_FROM", os.environ["SMTP_USER"])
    msg["To"] = args.to
    msg.set_content("Your weekly local search report is attached as HTML. Open it in any browser.")
    msg.add_attachment(report.render(cfg, Store(args.db)).encode(), maintype="text", subtype="html", filename="local-rankings.html")
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587)), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)
    print(f"Report emailed to {args.to}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rank-tracker", description="Track local Google rankings and reviews over time.")
    p.add_argument("--config", default="tracker.toml")
    p.add_argument("--db", default="rankings.sqlite")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="Create an example config file")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("find", help="Find a business's place id")
    s.add_argument("query")
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("check", help="Run a ranking check now (or for --date)")
    s.add_argument("--date", help="YYYY-MM-DD (default today)")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("demo", help="Record weeks of simulated checks (demo provider only)")
    s.add_argument("--weeks", type=int, default=16)
    s.add_argument("--start", default="2026-06-01")
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("report", help="Write the HTML report")
    s.add_argument("--out", default="report.html")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("email", help="Email the HTML report")
    s.add_argument("--to", required=True)
    s.set_defaults(func=cmd_email)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
