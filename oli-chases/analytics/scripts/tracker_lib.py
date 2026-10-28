"""Shared schema + append-only CSV helpers for the @oli.chases measurement tracker.

Rules enforced here (see measurement_readme.md):
- Snapshots are append-only; (content_id, snapshot_at, data_source) is unique.
- Missing values stay blank. Never coerce blank -> 0.
- Only @oli.chases (IG user id 17841431932380351) rows enter the formal tables.
"""
import csv
import os
import re
from datetime import datetime, timezone

ANALYTICS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OLI_CHASES_IG_USER_ID = "17841431932380351"
OLI_CHASES_ACCOUNT = "oli.chases"
# Handles that refer to the same account (MBS shows the underscore form).
OLI_CHASES_HANDLES = {"oli.chases", "oli_chases", "@oli.chases", "@oli_chases"}
# Accounts that must never be mixed into @oli.chases analysis.
EXCLUDED_ACCOUNTS = {"oli.remote.diary", "@oli.remote.diary"}

PILLARS = ["Culture Observation", "Overseas Workplace Truth", "Life Insight"]

REGISTRY_FILE = os.path.join(ANALYTICS_DIR, "content_registry.csv")
SNAPSHOT_FILE = os.path.join(ANALYTICS_DIR, "performance_snapshots.csv")
CONVERSION_FILE = os.path.join(ANALYTICS_DIR, "conversion_events.csv")
FETCH_LOG_FILE = os.path.join(ANALYTICS_DIR, "fetch_log.csv")
EXCLUDED_FILE = os.path.join(ANALYTICS_DIR, "excluded_rows.csv")

REGISTRY_FIELDS = [
    "content_id", "platform", "account", "permalink", "published_at", "pillar",
    "sub_pillar", "format", "topic", "cta_type", "cta_keyword", "utm_campaign",
    "conversion_destination", "content_status", "notes",
]
SNAPSHOT_FIELDS = [
    "snapshot_at", "content_id", "age_hours", "views", "reach",
    "non_follower_reach", "profile_visits", "follows", "likes", "comments",
    "shares", "saves", "avg_watch_time", "retention_or_skip_rate",
    "data_source", "data_status",
]
CONVERSION_FIELDS = [
    "event_at", "content_id", "conversion_type", "conversion_count",
    "attribution_method", "utm_campaign", "notes",
]
FETCH_LOG_FIELDS = [
    "run_at", "source", "content_id", "status", "missing_fields", "error",
]
EXCLUDED_FIELDS = ["logged_at", "source", "source_row", "identifier", "reason"]

CONVERSION_TYPES = {
    "newsletter_signup", "qualified_inquiry", "workshop_registration", "purchase",
    # Funnel steps that are NOT final conversions; tracked so they are not
    # mistaken for registrations/signups.
    "workshop_waitlist", "manychat_keyword_trigger",
}
ATTRIBUTION_METHODS = {
    "direct_utm", "manychat_keyword", "self_reported", "campaign_level",
    "time_window", "unattributed",
}


def content_id_from_permalink(permalink):
    m = re.search(r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", permalink or "")
    return f"ig_{m.group(1)}" if m else ""


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ensure_file(path, fields):
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()


def append_rows(path, fields, rows):
    ensure_file(path, fields)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="raise")
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def snapshot_key(row):
    return (row["content_id"], row["snapshot_at"], row["data_source"])


def append_snapshots(rows):
    """Append snapshots, skipping any whose (content_id, snapshot_at, data_source) exists."""
    existing = {snapshot_key(r) for r in read_rows(SNAPSHOT_FILE)}
    new = []
    for r in rows:
        k = snapshot_key(r)
        if k in existing:
            continue
        existing.add(k)
        new.append(r)
    append_rows(SNAPSHOT_FILE, SNAPSHOT_FIELDS, new)
    return new


def upsert_registry(rows):
    """Add registry rows for unseen content_ids. Existing rows are never overwritten
    (manual tagging wins); returns the list of newly added rows."""
    existing = {r["content_id"] for r in read_rows(REGISTRY_FILE)}
    new = [r for r in rows if r["content_id"] not in existing]
    append_rows(REGISTRY_FILE, REGISTRY_FIELDS, new)
    return new


def append_conversions(rows):
    """Append conversion rows, skipping exact duplicates."""
    def key(r):
        return tuple(str(r.get(k, "")) for k in CONVERSION_FIELDS)
    existing = {key(r) for r in read_rows(CONVERSION_FILE)}
    new = [r for r in rows if key(r) not in existing]
    for r in new:
        if r["conversion_type"] not in CONVERSION_TYPES:
            raise ValueError(f"unknown conversion_type {r['conversion_type']!r}")
        if r["attribution_method"] not in ATTRIBUTION_METHODS:
            raise ValueError(f"unknown attribution_method {r['attribution_method']!r}")
    append_rows(CONVERSION_FILE, CONVERSION_FIELDS, new)
    return new


def log_excluded(rows):
    def key(r):
        return (r["source"], str(r["source_row"]))
    existing = {key(r) for r in read_rows(EXCLUDED_FILE)}
    new = [r for r in rows if key(r) not in existing]
    append_rows(EXCLUDED_FILE, EXCLUDED_FIELDS, new)
    return new


def clean_number(value):
    """Keep source numbers as-is; blank / 'n/a' stays blank (never 0)."""
    v = (value or "").strip().replace(",", "")
    if v.lower() in {"", "n/a", "na", "-", "--", "null", "none"}:
        return ""
    return v


def parse_loose_dt(value):
    """Parse 'YYYY-MM-DD H:MM[:SS]' strings (timezone-naive). Returns None if unparseable."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S+0000"):
        try:
            return datetime.strptime((value or "").strip(), fmt)
        except ValueError:
            continue
    return None
