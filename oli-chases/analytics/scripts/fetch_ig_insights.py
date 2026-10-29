"""Fetch Instagram media Insights for @oli.chases via the official Instagram Graph API
and append snapshot rows (never overwrites).

Env (GitHub Secrets in CI):
  IG_ACCESS_TOKEN  long-lived token with instagram_basic + instagram_manage_insights
                   (or instagram_business_basic + instagram_business_manage_insights)
  IG_USER_ID       optional, defaults to 17841431932380351 (@oli.chases)
  IG_GRAPH_HOST    optional, graph.facebook.com (Facebook Login token, default)
                   or graph.instagram.com (Instagram Login token)
  IG_API_VERSION   optional, default v21.0

All media insights are LIFETIME cumulative values (no time window). Each row records its
capture time in snapshot_at (UTC, minute precision); never read a row as that hour's increment.

Cadence: hourly while a post is <= 48h old; then at most one snapshot per UTC day up to day 14;
then once on days 21/30/60/90. At most one snapshot per content per UTC hour.
Metrics the API refuses for a media type are left blank and listed as unavailable.
At most one retry on 429/5xx; failures are logged to fetch_log.csv and never written as 0.

Metric names follow the ones verified against the Muse `individual-post-insights` raw response
(see measurement_readme.md). Public names are tried only as a fallback and recorded in data_status.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import tracker_lib as t

DATA_SOURCE = "ig_graph_api"
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
USER_ID = os.environ.get("IG_USER_ID", t.OLI_CHASES_IG_USER_ID)
HOST = os.environ.get("IG_GRAPH_HOST", "graph.facebook.com")
VERSION = os.environ.get("IG_API_VERSION", "v21.0")
LOOKBACK_DAYS = 95
HOURLY_UNTIL_H = 48
DAILY_UNTIL_D = 14
LATE_CHECKPOINT_DAYS = {21, 30, 60, 90}

# snapshot column -> (primary metric, public fallback or None). Values are stored as returned.
COMMON_METRICS = {
    "views": ("instagram_organic_media_content_views_count", "views"),   # organic views
    "follows": ("instagram_organic_media_follow_count", "follows"),
    "profile_visits": ("instagram_media_profile_views_from_impressions_count", "profile_visits"),
    "reach": ("reach", None),
    "likes": ("likes", None),
    "comments": ("comments", None),
    "shares": ("shares", None),
    "saves": ("saved", None),
}
# Reel-only; never requested for carousels / images.
REEL_METRICS = {
    "plays": ("ig_clips_play_count", None),
    "replays": ("instagram_clips_video_replay_count", None),
    "retention_or_skip_rate": ("ig_reels_skip_rate", None),     # decimal: 0.3478 = 34.78%
    "avg_watch_time": ("ig_reels_avg_watch_time", None),       # unit unknown: do NOT treat as seconds
}
VIEWS_METRIC = COMMON_METRICS["views"][0]
# Graph API has no per-media non-follower REACH; we store non-follower VIEWS from the views breakdown.
NEVER_AVAILABLE = ["non_follower_reach"]


class ApiError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


def _scrub(text):
    return re.sub(r"access_token=[^&\s\"]+", "access_token=***", str(text))


def api_get(path, params, retried=False):
    q = urllib.parse.urlencode({**params, "access_token": TOKEN})
    url = f"https://{HOST}/{VERSION}/{path}?{q}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            err = json.loads(body).get("error", {})
        except ValueError:
            err = {"message": body[:200]}
        if (e.code == 429 or e.code >= 500) and not retried:
            time.sleep(5)
            return api_get(path, params, retried=True)
        raise ApiError(_scrub(f"HTTP {e.code}: {err.get('message', '')}"), err.get("code"))
    except urllib.error.URLError as e:
        if not retried:
            time.sleep(5)
            return api_get(path, params, retried=True)
        raise ApiError(_scrub(f"network: {e.reason}"))


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def list_recent_media(now):
    media, params, path = [], {"fields": "id,caption,media_type,media_product_type,permalink,timestamp",
                               "limit": 50}, f"{USER_ID}/media"
    for _ in range(10):  # hard page cap
        data = api_get(path, params)
        for m in data.get("data", []):
            if (now - parse_ts(m["timestamp"])).days > LOOKBACK_DAYS:
                return media
            media.append(m)
        nxt = data.get("paging", {}).get("cursors", {}).get("after")
        if not nxt or not data.get("paging", {}).get("next"):
            break
        params = {**params, "after": nxt}
    return media


def _item_value(item):
    if item.get("values"):
        return item["values"][0].get("value")
    return item.get("total_value", {}).get("value")


def non_follower_views(item):
    """Extract non_follower count from the organic views breakdown. None if absent."""
    bd = item.get("organic_follower_breakdown") or item.get("total_value", {}).get("organic_follower_breakdown")
    if isinstance(bd, dict) and bd.get("non_follower") is not None:
        return bd["non_follower"]
    for b in item.get("total_value", {}).get("breakdowns", []) or []:
        for res in b.get("results", []):
            if "non_follower" in [str(d).lower() for d in res.get("dimension_values", [])]:
                return res.get("value")
    return None


def _get_metric(media_id, name):
    """Returns the insight item, or None if the API rejects this metric for this media."""
    try:
        data = api_get(f"{media_id}/insights", {"metric": name})
    except ApiError as e:
        if e.code in (100, 10):
            return None
        raise
    items = [i for i in data.get("data", []) if i.get("name") == name]
    return items[0] if items else None


def fetch_insights(media_id, spec):
    """spec: column -> (primary, fallback). One metric per call so a rejected metric never
    hides the others. Returns (values, unavailable_columns, status_tokens)."""
    values, unavailable, tokens = {}, [], []
    for col, (primary, fallback) in spec.items():
        item, used = _get_metric(media_id, primary), primary
        if item is None and fallback:
            item, used = _get_metric(media_id, fallback), fallback
            if item is not None:
                tokens.append(f"{col}_metric={fallback}")
        if item is None or _item_value(item) is None:
            unavailable.append(col)
            continue
        values[col] = _item_value(item)
        if col == "views" and used == VIEWS_METRIC:
            nf = non_follower_views(item)
            if nf is not None:
                values["non_follower_views"] = nf
    if "views" in values and "non_follower_views" not in values:
        unavailable.append("non_follower_views")
    return values, unavailable, tokens


def should_snapshot(age_h, last_capture, now):
    """last_capture: datetime of this content's latest ig_graph_api snapshot, or None."""
    if last_capture and last_capture.strftime("%Y%m%d%H") == now.strftime("%Y%m%d%H"):
        return False
    if age_h <= HOURLY_UNTIL_H:
        return True
    same_day = last_capture is not None and last_capture.date() == now.date()
    if age_h <= DAILY_UNTIL_D * 24:
        return not same_day
    return int(age_h // 24) in LATE_CHECKPOINT_DAYS and not same_day


def last_captures():
    out = {}
    for r in t.read_rows(t.SNAPSHOT_FILE):
        if r["data_source"] != DATA_SOURCE:
            continue
        try:
            dt = datetime.strptime(r["snapshot_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if r["content_id"] not in out or dt > out[r["content_id"]]:
            out[r["content_id"]] = dt
    return out


def detect_cta_keyword(caption):
    m = re.search(r"留言\s*[「『\"“]([^」』\"”]+)[」』\"”]", caption or "")
    return m.group(1) if m else ""


def main():
    run_at = t.utc_now_iso()
    if not TOKEN:
        t.append_rows(t.FETCH_LOG_FILE, t.FETCH_LOG_FIELDS, [{
            "run_at": run_at, "source": DATA_SOURCE, "content_id": "*", "status": "skipped",
            "missing_fields": "", "error": "IG_ACCESS_TOKEN not set; no automatic fetch performed"}])
        print("IG_ACCESS_TOKEN not set; skipped (logged).")
        return 0
    now = datetime.now(timezone.utc)
    snapshot_at = now.strftime("%Y-%m-%dT%H:%M:00Z")  # actual capture time
    last = last_captures()
    logs = []
    try:
        who = api_get(USER_ID, {"fields": "id,username"})
        if who.get("username", "").lower() not in t.OLI_CHASES_HANDLES:
            raise ApiError(f"token resolves to account {who.get('username')!r}, not @oli.chases; aborting")
        media = list_recent_media(now)
    except ApiError as e:
        t.append_rows(t.FETCH_LOG_FILE, t.FETCH_LOG_FIELDS, [{
            "run_at": run_at, "source": DATA_SOURCE, "content_id": "*", "status": "error",
            "missing_fields": "", "error": str(e)}])
        print(f"fetch failed: {e}")
        return 1

    registry, snaps = [], []
    for m in media:
        cid = t.content_id_from_permalink(m.get("permalink", ""))
        published = parse_ts(m["timestamp"])
        age_h = (now - published).total_seconds() / 3600
        if not cid or not should_snapshot(age_h, last.get(cid), now):
            continue
        kw = detect_cta_keyword(m.get("caption"))
        is_reel = (m.get("media_product_type") or "") == "REELS"
        registry.append({
            "content_id": cid, "platform": "instagram", "account": t.OLI_CHASES_ACCOUNT,
            "permalink": m["permalink"], "published_at": m["timestamp"], "pillar": "", "sub_pillar": "",
            "format": m.get("media_product_type") or m.get("media_type", ""),
            "topic": (m.get("caption") or "").replace("\n", " ")[:60],
            "cta_type": "manychat_comment" if kw else "", "cta_keyword": kw, "utm_campaign": "",
            "conversion_destination": "", "content_status": "needs_tagging",
            "notes": f"media_id={m['id']}; auto-added by fetch_ig_insights; published_at is API UTC",
        })
        spec = {**COMMON_METRICS, **(REEL_METRICS if is_reel else {})}
        try:
            values, unavailable, tokens = fetch_insights(m["id"], spec)
        except ApiError as e:
            logs.append({"run_at": run_at, "source": DATA_SOURCE, "content_id": cid, "status": "error",
                         "missing_fields": "", "error": str(e)})
            continue
        row = {"snapshot_at": snapshot_at, "content_id": cid, "age_hours": f"{age_h:.1f}",
               "data_source": DATA_SOURCE}
        for col in t.SNAPSHOT_FIELDS:
            if col not in ("snapshot_at", "content_id", "age_hours", "data_source", "data_status"):
                v = values.get(col)
                row[col] = "" if v is None else v
        not_applicable = [] if is_reel else list(REEL_METRICS)
        missing = sorted(set(unavailable + NEVER_AVAILABLE))
        scope = "total" if "views_metric=views" in tokens else "organic"
        status = ["ok", "lifetime_cumulative", f"views_scope={scope}"] + tokens
        if is_reel:
            status += ["skip_rate=decimal", "avg_watch_time_unit=unknown"]
        status.append("unavailable=" + ",".join(missing))
        if not_applicable:
            status.append("not_applicable=" + ",".join(not_applicable))
        row["data_status"] = ";".join(status)
        snaps.append(row)
        logs.append({"run_at": run_at, "source": DATA_SOURCE, "content_id": cid, "status": "ok",
                     "missing_fields": ",".join(missing), "error": ""})

    t.upsert_registry(registry)
    added = t.append_snapshots(snaps)
    added_ids = {r["content_id"] for r in added}
    for l in logs:
        if l["status"] == "ok" and l["content_id"] not in added_ids:
            l["status"] = "duplicate_skipped"
    if not logs:
        logs.append({"run_at": run_at, "source": DATA_SOURCE, "content_id": "*", "status": "ok_no_due_media",
                     "missing_fields": "", "error": ""})
    t.append_rows(t.FETCH_LOG_FILE, t.FETCH_LOG_FIELDS, logs)
    print(f"media checked {len(media)}, snapshots +{len(added)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
