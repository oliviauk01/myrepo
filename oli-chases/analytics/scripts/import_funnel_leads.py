"""Aggregate ManyChat/Make lead rows ('oli.chases Funnel Tracking' Sheet) into conversion_events.csv.

Usage:
  python3 import_funnel_leads.py sources/funnel_tracking_extract_2026-10-28.csv   # PII-free extract
  python3 import_funnel_leads.py raw/funnel_tracking_raw.csv                       # raw Sheet export (gitignored)

Only daily aggregate counts are written. Emails / usernames / names never leave this script.
Test rows and internal accounts (e.g. @oli.remote.diary) are excluded and logged by row number.

Mapping:
  cta *subscribe* + email captured        -> newsletter_signup (email captured via ManyChat; Beehiiv
                                             confirmation not verified)
  cta *webinar* / *waitlist* + email      -> workshop_waitlist (NOT workshop_registration: a link/waitlist
                                             request is not a confirmed registration)
  no email captured                       -> manychat_keyword_trigger
Attribution:
  source_post maps to a content_id + entry_point=post_comment -> manychat_keyword
  source_post maps to a content_id (other entry)              -> direct_utm
  no content match but a campaign                             -> campaign_level
  otherwise                                                   -> unattributed
"""
import csv
import os
import re
import sys
from collections import Counter

import tracker_lib as t

INTERNAL_USERNAMES = {"oli.remote.diary", "olivia_lee_hsien", "olivia_lee122", "chasedream22", "test_account"}


def classify_raw(r):
    """For raw exports: derive has_email + excluded_reason without keeping PII."""
    email = (r.get("email") or "").strip().lower()
    user = (r.get("instagram_username") or "").strip().lower()
    reason = ""
    if (r.get("idea_id") or "").startswith("test") or (r.get("source_post") or "").startswith("test"):
        reason = "test_row"
    elif "test" in email or email.startswith("oliviauk01"):
        reason = "test_email"
    elif user in INTERNAL_USERNAMES:
        reason = "internal_account" + ("_oli.remote.diary" if user == "oli.remote.diary" else "")
    return ("yes" if email else "no"), reason


def event_date(ts):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", (ts or "").strip())
    return m.group(1) if m else ""


def main(path):
    source_name = os.path.basename(path)
    campaign_to_content = {r["utm_campaign"]: r["content_id"]
                           for r in t.read_rows(t.REGISTRY_FILE) if r["utm_campaign"]}
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    is_extract = "has_email" in (rows[0].keys() if rows else [])

    counts, excluded = Counter(), []
    for i, r in enumerate(rows, start=2):
        if is_extract:
            has_email, reason, row_id = r["has_email"], r["excluded_reason"], r["row"]
        else:
            (has_email, reason), row_id = classify_raw(r), str(i)
        if reason:
            excluded.append({"logged_at": t.utc_now_iso(), "source": source_name, "source_row": row_id,
                             "identifier": r.get("source_post", ""), "reason": reason})
            continue
        cta = (r.get("cta") or "").lower()
        if has_email != "yes":
            ctype = "manychat_keyword_trigger"
        elif "subscribe" in cta:
            ctype = "newsletter_signup"
        elif "webinar" in cta or "webniar" in cta or "waitlist" in cta:
            ctype = "workshop_waitlist"
        else:
            excluded.append({"logged_at": t.utc_now_iso(), "source": source_name, "source_row": row_id,
                             "identifier": cta, "reason": "unknown_cta_needs_mapping"})
            continue
        source_post = (r.get("source_post") or "").strip()
        campaign = (r.get("campaign") or "").strip()
        content_id = campaign_to_content.get(source_post, "")
        if content_id and (r.get("entry_point") or "").strip() == "post_comment":
            method = "manychat_keyword"
        elif content_id:
            method = "direct_utm"
        elif campaign:
            method = "campaign_level"
        else:
            method = "unattributed"
        utm = source_post or campaign
        key = (event_date(r.get("timestamp")), content_id, ctype, method, utm,
               (r.get("entry_point") or "").strip(), (r.get("cta_keyword") or "").strip())
        counts[key] += 1

    conversions = []
    for (day, cid, ctype, method, utm, entry, kw), n in sorted(counts.items()):
        note = f"source={source_name}; entry_point={entry or 'blank'}; keyword={kw or 'blank'}; aggregate count, no PII"
        if not day:
            note += "; event timestamp missing in source"
        if ctype == "newsletter_signup":
            note += "; email captured via ManyChat, Beehiiv confirmation not verified"
        conversions.append({"event_at": day, "content_id": cid, "conversion_type": ctype,
                            "conversion_count": n, "attribution_method": method,
                            "utm_campaign": utm, "notes": note})
    added = t.append_conversions(conversions)
    t.log_excluded(excluded)
    t.append_rows(t.FETCH_LOG_FILE, t.FETCH_LOG_FIELDS, [{
        "run_at": t.utc_now_iso(), "source": f"import:{source_name}", "content_id": "*",
        "status": f"ok leads={sum(counts.values())} conversion_rows+{len(added)} excluded={len(excluded)}",
        "missing_fields": "", "error": "",
    }])
    print(f"leads kept {sum(counts.values())}, conversion rows +{len(added)}, excluded {len(excluded)}")


if __name__ == "__main__":
    main(sys.argv[1])
