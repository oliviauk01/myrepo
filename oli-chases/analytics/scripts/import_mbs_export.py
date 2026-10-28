"""Import a Meta Business Suite (MBS) content export CSV as lifetime snapshots.

Usage:
  python3 import_mbs_export.py raw/<mbs_export>.csv --as-of 2026-10-24 [--label mbs_2026]

- Put raw exports in analytics/raw/ (gitignored). Only derived, non-PII rows are committed.
- MBS values are cumulative "as of" the export date, so snapshot_at = --as-of (required).
  Different exports (e.g. 2025 data as of 2026-04-16 vs 2026 data as of 2026-10-24) become
  separate snapshot rows with their own data_source; nothing is merged or overwritten.
- Rows are kept only when Account ID == 17841431932380351 or the username is oli.chases/oli_chases.
  Anything else (incl. collab posts credited to @oli.remote.diary, Facebook rows) goes to excluded_rows.csv.
- Publish time is kept as the raw MBS string; timezone is NOT inferred.
- Duration < 10s is kept verbatim but flagged needs_review:duration_suspect.
"""
import argparse
import csv
import os

import tracker_lib as t

# Header candidates seen in MBS exports (English / zh-TW UI). Extend if your export differs.
COLS = {
    "post_id": ["Post ID", "貼文編號", "貼文 ID"],
    "account_id": ["Account ID", "帳號編號", "帳號 ID"],
    "account": ["Account username", "Account name", "帳號用戶名稱", "帳號名稱"],
    "platform": ["Platform", "平台"],
    "permalink": ["Permalink", "永久連結"],
    "published": ["Publish time", "發佈時間", "發布時間"],
    "type": ["Post type", "貼文類型"],
    "duration": ["Duration (sec)", "Duration (secs)", "持續時間（秒）", "長度（秒）"],
    "views": ["Views", "觀看次數"],
    "reach": ["Reach", "觸及人數"],
    "likes": ["Likes", "讚"],
    "comments": ["Comments", "留言"],
    "shares": ["Shares", "分享"],
    "saves": ["Saves", "儲存"],
    "follows": ["Follows", "追蹤"],
    "profile_visits": ["Profile visits", "個人檔案瀏覽次數", "個人檔案造訪次數"],
}


def pick(row, field):
    for c in COLS[field]:
        if c in row:
            return (row[c] or "").strip()
    return None  # column absent (distinct from blank value)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--as-of", required=True, help="date the cumulative values are valid for, YYYY-MM-DD")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    source = f"mbs_export:{a.label or os.path.basename(a.path)}"
    with open(a.path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    registry, snaps, excluded = [], [], []
    for i, r in enumerate(rows, start=2):
        acct_id, acct = pick(r, "account_id") or "", (pick(r, "account") or "").lower()
        platform = (pick(r, "platform") or "instagram").lower()
        ident = pick(r, "post_id") or pick(r, "permalink") or ""
        if "facebook" in platform:
            reason = "facebook_row_not_instagram"
        elif acct in t.EXCLUDED_ACCOUNTS or acct_id and acct_id != t.OLI_CHASES_IG_USER_ID:
            reason = f"other_account:{acct or acct_id}"
        elif acct_id != t.OLI_CHASES_IG_USER_ID and acct not in t.OLI_CHASES_HANDLES:
            reason = "account_unconfirmed_needs_review"
        else:
            reason = ""
        cid = t.content_id_from_permalink(pick(r, "permalink") or "")
        if not reason and not cid:
            reason = "no_permalink_cannot_identify"
        if reason:
            excluded.append({"logged_at": t.utc_now_iso(), "source": source, "source_row": i,
                             "identifier": ident, "reason": reason})
            continue
        status = ["ok", "cumulative_as_of_export", "timezone=unverified"]
        dur = t.clean_number(pick(r, "duration") or "")
        if dur:
            status.append(f"mbs_duration_sec={dur}")
            try:
                if float(dur) < 10:
                    status[0] = "needs_review:duration_suspect"
            except ValueError:
                pass
        values = {}
        missing = []
        for f_ in ["views", "reach", "likes", "comments", "shares", "saves", "follows", "profile_visits"]:
            v = pick(r, f_)
            if v is None:
                missing.append(f_)
            values[f_] = t.clean_number(v or "")
        if missing:
            status.append("not_in_source=" + ",".join(missing))
        snaps.append({"snapshot_at": a.as_of, "content_id": cid, "age_hours": "",
                      "non_follower_reach": "", "avg_watch_time": "", "retention_or_skip_rate": "",
                      "data_source": source, "data_status": ";".join(status), **values})
        registry.append({"content_id": cid, "platform": "instagram", "account": t.OLI_CHASES_ACCOUNT,
                         "permalink": pick(r, "permalink"), "published_at": pick(r, "published") or "",
                         "pillar": "", "sub_pillar": "", "format": pick(r, "type") or "", "topic": "",
                         "cta_type": "", "cta_keyword": "", "utm_campaign": "", "conversion_destination": "",
                         "content_status": "needs_tagging",
                         "notes": f"from {source}; post_id={ident}; published_at raw MBS string, timezone unverified"})
    added_reg = t.upsert_registry(registry)
    added = t.append_snapshots(snaps)
    t.log_excluded(excluded)
    t.append_rows(t.FETCH_LOG_FILE, t.FETCH_LOG_FIELDS, [{
        "run_at": t.utc_now_iso(), "source": f"import:{source}", "content_id": "*",
        "status": f"ok registry+{len(added_reg)} snapshots+{len(added)} excluded={len(excluded)}",
        "missing_fields": "age_hours,non_follower_reach,avg_watch_time,retention_or_skip_rate", "error": "",
    }])
    print(f"registry +{len(added_reg)}, snapshots +{len(added)}, excluded {len(excluded)}")


if __name__ == "__main__":
    main()
