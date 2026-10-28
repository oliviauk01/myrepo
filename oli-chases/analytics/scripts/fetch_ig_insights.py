"""Fetch Instagram media Insights for @oli.chases via the official Instagram Graph API
and append snapshot rows (never overwrites).

Env (GitHub Secrets in CI):
  IG_ACCESS_TOKEN  long-lived token with instagram_basic + instagram_manage_insights
                   (or instagram_business_basic + instagram_business_manage_insights)
  IG_USER_ID       optional, defaults to 17841431932380351 (@oli.chases)
  IG_GRAPH_HOST    optional, graph.facebook.com (Facebook Login token, default)
                   or graph.instagram.com (Instagram Login token)
  IG_API_VERSION   optional, default v21.0

Snapshot cadence per media: every run while age <= 14 days; afterwards once on days 21/30/60/90.
snapshot_at is the run time truncated to the hour (UTC), so re-runs within the hour are no-ops.
Metrics the API refuses for a media type are left blank and listed as unavailable.
At most one retry on 429/5xx; failures are logged to fetch_log.csv and never written as 0.
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
LATE_CHECKPOINT_DAYS = {21, 30, 60, 90}

# Graph metric name -> snapshot column
METRICS = {
    "views": "views", "reach": "reach", "likes": "likes", "comments": "comments",
    "shares": "shares", "saved": "saves", "profile_visits": "profile_visits",
    "follows": "follows", "ig_reels_avg_watch_time": "avg_watch_time",
}
# Not exposed per-media by the Graph API at all.
NEVER_AVAILABLE = ["non_follower_reach", "retention_or_skip_rate"]


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


def fetch_insights(media_id, metrics):
    """Request all metrics at once; if the API rejects the set, fall back per metric."""
    values, unavailable = {}, []
    try:
        data = api_get(f"{media_id}/insights", {"metric": ",".join(metrics)})
        for item in data.get("data", []):
            values[item["name"]] = item.get("values", [{}])[0].get("value", item.get("total_value", {}).get("value"))
    except ApiError as e:
        if e.code not in (100, 10):
            raise
        for m in metrics:
            try:
                data = api_get(f"{media_id}/insights", {"metric": m})
                for item in data.get("data", []):
                    values[item["name"]] = item.get("values", [{}])[0].get("value")
            except ApiError as e2:
                if e2.code in (100, 10):
                    unavailable.append(m)
                else:
                    raise
    for m in metrics:
        if m not in values and m not in unavailable:
            unavailable.append(m)
    return values, unavailable


def should_snapshot(age_days):
    return age_days <= 14 or age_days in LATE_CHECKPOINT_DAYS


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
    snapshot_at = now.strftime("%Y-%m-%dT%H:00:00Z")
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
        if not cid or not should_snapshot(int(age_h // 24)):
            continue
        kw = detect_cta_keyword(m.get("caption"))
        registry.append({
            "content_id": cid, "platform": "instagram", "account": t.OLI_CHASES_ACCOUNT,
            "permalink": m["permalink"], "published_at": m["timestamp"], "pillar": "", "sub_pillar": "",
            "format": m.get("media_product_type") or m.get("media_type", ""),
            "topic": (m.get("caption") or "").replace("\n", " ")[:60],
            "cta_type": "manychat_comment" if kw else "", "cta_keyword": kw, "utm_campaign": "",
            "conversion_destination": "", "content_status": "needs_tagging",
            "notes": f"media_id={m['id']}; auto-added by fetch_ig_insights; published_at is API UTC",
        })
        metrics = list(METRICS)
        if (m.get("media_product_type") or "") != "REELS":
            metrics.remove("ig_reels_avg_watch_time")
        try:
            values, unavailable = fetch_insights(m["id"], metrics)
        except ApiError as e:
            logs.append({"run_at": run_at, "source": DATA_SOURCE, "content_id": cid, "status": "error",
                         "missing_fields": "", "error": str(e)})
            continue
        row = {"snapshot_at": snapshot_at, "content_id": cid, "age_hours": f"{age_h:.1f}",
               "non_follower_reach": "", "retention_or_skip_rate": "", "avg_watch_time": "",
               "data_source": DATA_SOURCE}
        for api_name, col in METRICS.items():
            v = values.get(api_name)
            row[col] = "" if v is None else v
        missing = [METRICS[u] for u in unavailable] + NEVER_AVAILABLE
        if "ig_reels_avg_watch_time" not in metrics:
            missing.append("avg_watch_time")
        row["data_status"] = "ok;unavailable=" + ",".join(sorted(set(missing)))
        snaps.append(row)
        logs.append({"run_at": run_at, "source": DATA_SOURCE, "content_id": cid, "status": "ok",
                     "missing_fields": ",".join(sorted(set(missing))), "error": ""})

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
