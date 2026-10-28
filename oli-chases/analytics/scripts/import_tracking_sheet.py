"""Import a backup/export of the Google Sheet '@oli_chases IG 自動追蹤數據' (tab 貼文數據).

Usage:
  python3 import_tracking_sheet.py sources/ig_tracking_sheet_backup_2026-10-28.csv

- Source strings (publish time, tracked time) are kept verbatim; their timezone is the
  Apps Script timezone and is NOT verified, so no conversion is done.
- Metrics the Sheet never captured (views, follows, non-follower reach, watch time)
  stay blank and are flagged not_in_source.
- Derived columns (ER%, rates, Convert from Reach) are not imported; reports recompute them.
- Re-running is safe: duplicate (content_id, snapshot_at, data_source) rows are skipped.
"""
import csv
import os
import sys

import tracker_lib as t

DATA_SOURCE = "gsheet_ig_auto_tracking"
TAGGING_FILE = os.path.join(t.ANALYTICS_DIR, "sources", "content_tagging.csv")


def load_tagging():
    return {r["shortcode"]: r for r in t.read_rows(TAGGING_FILE)}


def age_hours(published, snapshot):
    p, s = t.parse_loose_dt(published), t.parse_loose_dt(snapshot)
    if not p or not s:
        return ""
    return f"{(s - p).total_seconds() / 3600:.1f}"


def main(path):
    tagging = load_tagging()
    source_name = os.path.basename(path)
    registry, snapshots, conversions, excluded = [], [], [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows, start=2):
        cid = t.content_id_from_permalink(r["連結"])
        if not cid:
            excluded.append({"logged_at": t.utc_now_iso(), "source": source_name, "source_row": i,
                             "identifier": r.get("貼文ID", ""), "reason": "no_permalink_cannot_identify"})
            continue
        shortcode = cid[3:]
        tag = tagging.get(shortcode, {})
        media_id = r["貼文ID"].strip()
        notes = [f"media_id={media_id}"]
        if "E+" in media_id.upper():
            notes = [f"media_id_corrupted_in_sheet={media_id} (resolve via Graph API by permalink)"]
        notes.append(f"published_at is source string; timezone=unverified ({DATA_SOURCE})")
        if tag.get("notes"):
            notes.append(tag["notes"])
        registry.append({
            "content_id": cid, "platform": "instagram", "account": t.OLI_CHASES_ACCOUNT,
            "permalink": r["連結"].strip(), "published_at": r["發布時間"].strip(),
            "pillar": tag.get("pillar", ""), "sub_pillar": tag.get("sub_pillar", ""),
            "format": r["類型"].strip(), "topic": tag.get("topic", ""),
            "cta_type": tag.get("cta_type", ""), "cta_keyword": tag.get("cta_keyword", ""),
            "utm_campaign": tag.get("utm_campaign", ""),
            "conversion_destination": tag.get("conversion_destination", ""),
            "content_status": "published" if tag.get("pillar") else "needs_tagging",
            "notes": "; ".join(notes),
        })

        snap_at = r["追蹤時間"].strip()
        status = [f"sheet_label={r['快照'].strip()}", "timezone=unverified",
                  "not_in_source=views,follows,non_follower_reach,avg_watch_time,retention_or_skip_rate"]
        if not snap_at:
            status.insert(0, "needs_review:snapshot_time_missing")
        else:
            status.insert(0, "ok")
        if not t.clean_number(r["Profile Visits"]):
            status.append("missing=profile_visits")
        snapshots.append({
            "snapshot_at": snap_at, "content_id": cid,
            "age_hours": age_hours(r["發布時間"], snap_at),
            "views": "", "reach": t.clean_number(r["Reach"]), "non_follower_reach": "",
            "profile_visits": t.clean_number(r["Profile Visits"]), "follows": "",
            "likes": t.clean_number(r["Likes"]), "comments": t.clean_number(r["Comments"]),
            "shares": t.clean_number(r["Shares"]), "saves": t.clean_number(r["Saves"]),
            "avg_watch_time": "", "retention_or_skip_rate": "",
            "data_source": DATA_SOURCE, "data_status": ";".join(status),
        })

        subs_ig = t.clean_number(r.get("其中來自IG", ""))
        subs_total = t.clean_number(r.get("Beehiiv新增訂閱(24h)", ""))
        if subs_ig:
            note = (f"Beehiiv new subs in window after post; total={subs_total}, from_ig={subs_ig}; "
                    f"source={DATA_SOURCE} label={r['快照'].strip()}; window-based, not per-subscriber attribution")
            if r.get("備註"):
                note += f"; source_note={r['備註'].strip()}"
            conversions.append({
                "event_at": snap_at, "content_id": cid, "conversion_type": "newsletter_signup",
                "conversion_count": subs_ig, "attribution_method": "time_window",
                "utm_campaign": tag.get("utm_campaign", ""), "notes": note,
            })

    # De-dupe registry rows within this file (multiple snapshots per post).
    seen, uniq = set(), []
    for r in registry:
        if r["content_id"] not in seen:
            seen.add(r["content_id"])
            uniq.append(r)
    added_reg = t.upsert_registry(uniq)
    added_snap = t.append_snapshots(snapshots)
    added_conv = t.append_conversions(conversions)
    t.log_excluded(excluded)
    t.append_rows(t.FETCH_LOG_FILE, t.FETCH_LOG_FIELDS, [{
        "run_at": t.utc_now_iso(), "source": f"import:{source_name}", "content_id": "*",
        "status": f"ok registry+{len(added_reg)} snapshots+{len(added_snap)} conversions+{len(added_conv)} excluded={len(excluded)}",
        "missing_fields": "views,follows,non_follower_reach,avg_watch_time,retention_or_skip_rate",
        "error": "",
    }])
    print(f"registry +{len(added_reg)}, snapshots +{len(added_snap)} (of {len(snapshots)}), "
          f"conversions +{len(added_conv)}, excluded {len(excluded)}")


if __name__ == "__main__":
    main(sys.argv[1])
