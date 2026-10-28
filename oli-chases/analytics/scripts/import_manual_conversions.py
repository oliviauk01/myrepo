"""Append manually reported conversions (UTM signups, ManyChat triggers, workshop registrations,
qualified inquiries, purchases) from a CSV in the conversion_events schema.

Usage: python3 import_manual_conversions.py sources/manual_conversions.csv
Template: sources/manual_conversions_template.csv. Aggregate counts only — no names/emails.
Rows with unknown conversion_type / attribution_method are rejected (whole file aborts).
Blank content_id is allowed (campaign_level / unattributed); do not guess a post.
"""
import sys

import tracker_lib as t

rows = t.read_rows(sys.argv[1])
for i, r in enumerate(rows, start=2):
    if set(r) != set(t.CONVERSION_FIELDS):
        sys.exit(f"row {i}: columns must be exactly {t.CONVERSION_FIELDS}")
    if r["attribution_method"] in ("direct_utm", "manychat_keyword") and not r["content_id"]:
        sys.exit(f"row {i}: {r['attribution_method']} requires content_id")
    if "@" in r["notes"]:
        sys.exit(f"row {i}: notes look like they contain an email; store aggregates only")
added = t.append_conversions(rows)
t.append_rows(t.FETCH_LOG_FILE, t.FETCH_LOG_FIELDS, [{
    "run_at": t.utc_now_iso(), "source": f"import:{sys.argv[1]}", "content_id": "*",
    "status": f"ok conversion_rows+{len(added)}", "missing_fields": "", "error": ""}])
print(f"conversion rows +{len(added)}")
