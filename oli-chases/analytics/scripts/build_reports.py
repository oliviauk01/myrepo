"""Build reports/measurement_report.md and daily_measurement_brief.md from the tracker CSVs.

Usage: python3 build_reports.py [--today YYYY-MM-DD]

Rules: rates are blank when numerator/denominator is missing or denominator is 0;
nothing is ranked by views/reach; groups with n < MIN_N are labelled 方向性訊號／樣本不足;
only snapshots whose data_status starts with 'ok' enter the analysis; sources are never merged.
"""
import argparse
import os
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import tracker_lib as t

MIN_N = 5
REPORT_FILE = os.path.join(t.ANALYTICS_DIR, "reports", "measurement_report.md")
BRIEF_FILE = os.path.join(t.ANALYTICS_DIR, "daily_measurement_brief.md")
FORMAL_ATTRIBUTION = {"direct_utm", "manychat_keyword"}
FINAL_CONVERSIONS = ["newsletter_signup", "qualified_inquiry", "workshop_registration", "purchase"]


def num(v):
    try:
        return float(v) if str(v).strip() != "" else None
    except ValueError:
        return None


def ratio(n, d):
    n, d = num(n), num(d)
    if n is None or d is None or d == 0:
        return None
    return n / d


def pct(x, digits=2):
    return "" if x is None else f"{x * 100:.{digits}f}%"


def med(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def bucket(age):
    a = num(age)
    if a is None:
        return "cumulative"
    if a <= 3:
        return "~1h"
    if 18 <= a <= 30:
        return "~24h"
    if 30 < a <= 200:
        return "2-8d"
    if a > 200:
        return "8d+"
    return "3-18h"


def sample_flag(n):
    return "方向性訊號／樣本不足" if n < MIN_N else f"n={n}（仍屬描述性，非統計顯著）"


def load():
    registry = {r["content_id"]: r for r in t.read_rows(t.REGISTRY_FILE)
                if r["account"] == t.OLI_CHASES_ACCOUNT and r["platform"] == "instagram"}
    snaps_all = t.read_rows(t.SNAPSHOT_FILE)
    snaps = [s for s in snaps_all if s["data_status"].startswith("ok") and s["content_id"] in registry]
    conv = t.read_rows(t.CONVERSION_FILE)
    log = t.read_rows(t.FETCH_LOG_FILE)
    return registry, snaps_all, snaps, conv, log


def latest_per(snaps):
    """(content_id, bucket, data_source) -> latest snapshot in that bucket."""
    best = {}
    for s in snaps:
        k = (s["content_id"], bucket(s["age_hours"]), s["data_source"])
        if k not in best or (num(s["age_hours"]) or 0) >= (num(best[k]["age_hours"]) or 0):
            best[k] = s
    return best


def rates(s):
    return {
        "follows/reach": ratio(s["follows"], s["reach"]),
        "profile_visits/reach": ratio(s["profile_visits"], s["reach"]),
        "follows/profile_visits": ratio(s["follows"], s["profile_visits"]),
        "shares/reach": ratio(s["shares"], s["reach"]),
        "saves/reach": ratio(s["saves"], s["reach"]),
        # Only organic views carry the follower breakdown.
        "non_follower_views/views": ratio(s.get("non_follower_views"), s["views"])
        if "views_scope=organic" in s["data_status"] else None,
    }


RATE_KEYS = ["follows/reach", "profile_visits/reach", "follows/profile_visits", "shares/reach", "saves/reach",
             "non_follower_views/views"]


def attributable(conv):
    out = defaultdict(lambda: defaultdict(float))
    for c in conv:
        if c["content_id"] and c["attribution_method"] in FORMAL_ATTRIBUTION:
            out[c["content_id"]][c["conversion_type"]] += num(c["conversion_count"]) or 0
    return out


def group_table(title, rows, key_fn, registry, attr):
    groups = defaultdict(list)
    for (cid, _b, _src), s in rows:
        groups[key_fn(registry[cid])].append((cid, s))
    lines = [f"#### {title}", "",
             "| 群組 | 內容數 | 中位 follows/reach | 中位 PV/reach | 中位 follows/PV | 中位 shares/reach | 中位 saves/reach | 中位 non-follower views % | 可歸因轉換（direct_utm+manychat_keyword） | 樣本 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for g in sorted(groups):
        items = groups[g]
        r = [rates(s) for _, s in items]
        conv_n = sum(sum(attr[cid].get(ct, 0) for ct in FINAL_CONVERSIONS) for cid in {c for c, _ in items})
        lines.append(f"| {g or '（未標記）'} | {len(items)} | " + " | ".join(
            pct(med([x[k] for x in r])) for k in RATE_KEYS) + f" | {int(conv_n) if conv_n else ''} | {sample_flag(len(items))} |")
    return lines + [""]


def build_report(registry, snaps_all, snaps, conv, today):
    best = latest_per(snaps)
    attr = attributable(conv)
    L = ["# @oli.chases Measurement Report", "",
         f"_自動產生：{today}（build_reports.py）。核心目標 Follow → Convert；Views/Reach 只作診斷。_", "",
         "比率規則：分母為 0 或欄位缺失 → 空白（不是 0%）。表格依發布時間排序，不依 Views/Reach 排名。", ""]

    sources = sorted({k[2] for k in best})
    for src in sources:
        L += [f"## 來源：`{src}`", ""]
        for b in ["~1h", "3-18h", "~24h", "2-8d", "8d+", "cumulative"]:
            rows = [(k, s) for k, s in best.items() if k[1] == b and k[2] == src]
            if not rows:
                continue
            rows.sort(key=lambda kv: registry[kv[0][0]]["published_at"])
            L += [f"### Snapshot age：{b}（{len(rows)} 篇，{sample_flag(len(rows))}）", "",
                  "| content_id | 發布(來源字串) | pillar | format | CTA | reach | PV | follows | follows/reach | PV/reach | follows/PV | shares/reach | saves/reach | non-follower views % | 3s skip rate（Reel） |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for (cid, _b, _s), s in rows:
                reg, r = registry[cid], rates(s)
                cta = "/".join(x for x in [reg["cta_type"], reg["cta_keyword"]] if x)
                L.append(f"| {cid} | {reg['published_at']} | {reg['pillar']} | {reg['format']} | {cta} | "
                         f"{s['reach']} | {s['profile_visits']} | {s['follows']} | " +
                         " | ".join(pct(r[k]) for k in RATE_KEYS) +
                         f" | {pct(num(s['retention_or_skip_rate']))} |")  # API returns a decimal
            L.append("")
            L += group_table("依 pillar", rows, lambda r: r["pillar"], registry, attr)
            L += group_table("依年份", rows, lambda r: r["published_at"][:4], registry, attr)
            L += group_table("依 CTA", rows, lambda r: r["cta_type"] or "no_cta", registry, attr)

    L += ["## 轉換（依類型 × 歸因方式）", "",
          "| conversion_type | attribution_method | 總數 | 列數 |", "|---|---|---|---|"]
    agg = defaultdict(lambda: [0.0, 0])
    for c in conv:
        a = agg[(c["conversion_type"], c["attribution_method"])]
        a[0] += num(c["conversion_count"]) or 0
        a[1] += 1
    for (ct, am), (n, rows) in sorted(agg.items()):
        L.append(f"| {ct} | {am} | {int(n)} | {rows} |")
    L += ["", "`workshop_waitlist`、`manychat_keyword_trigger` 是漏斗中間步驟，不等於報名或訂閱。",
          "`time_window`、`campaign_level` 不歸給單篇內容；只有 `direct_utm`、`manychat_keyword` 進入單篇轉換率。", ""]

    L += ["## 轉換 / Follows（僅歸因可信時計算）", "",
          "| content_id | follows（最新可用） | " + " | ".join(FINAL_CONVERSIONS) + " | " +
          " | ".join(f"{c}/follows" for c in FINAL_CONVERSIONS) + " |",
          "|---|---|" + "---|" * (2 * len(FINAL_CONVERSIONS))]
    for cid in sorted(attr, key=lambda c: registry.get(c, {}).get("published_at", "")):
        if cid not in registry:
            continue
        fol = [s for s in snaps if s["content_id"] == cid and num(s["follows"]) is not None]
        follows = max(fol, key=lambda s: num(s["age_hours"]) or 0)["follows"] if fol else ""
        counts = [attr[cid].get(c, 0) for c in FINAL_CONVERSIONS]
        L.append(f"| {cid} | {follows} | " + " | ".join(str(int(x)) if x else "" for x in counts) + " | " +
                 " | ".join(pct(ratio(x, follows)) if x else "" for x in counts) + " |")
    L += ["", "follows 空白 → 轉換率空白（歷史 Sheet 未記錄 follows）。不同 CTA、觀察期、來源之間不比較轉換率。", ""]

    review = [s for s in snaps_all if not s["data_status"].startswith("ok")]
    untagged = [r for r in registry.values() if not r["pillar"]]
    inferred = [r for r in registry.values() if "pillar_inferred" in r["notes"]]
    L += ["## 資料品質", "",
          f"- 待確認（不進正式分析）的快照：{len(review)} 列",
          f"- 未標記 pillar 的內容：{len(untagged)} 篇；pillar 為推論待確認：{len(inferred)} 篇",
          "- 歷史 Sheet 未記錄：views、follows、non_follower_reach、avg_watch_time、retention",
          "- Graph API 數值皆為 lifetime 累計；snapshot_at 是抓取時間，相鄰快照差值才是區間增量",
          "- avg_watch_time 單位未知，未當秒數使用；Graph API 無單篇 non-follower reach（以 non-follower views 代替，欄位分開）",
          "- Sheet 發布/追蹤時間為 Apps Script 時區字串，未經官方欄位證實；未做時區轉換", ""]
    return "\n".join(L) + "\n"


def build_brief(registry, snaps_all, snaps, conv, log, today):
    best = latest_per(snaps)
    attr = attributable(conv)
    today_rows = [s for s in snaps_all if s["snapshot_at"][:10] == today]
    today_api = [s for s in today_rows if s["data_source"] == "ig_graph_api"]
    today_logs = [l for l in log if l["run_at"][:10] == today]
    cutoffs = defaultdict(str)
    for s in snaps:
        cutoffs[s["data_source"]] = max(cutoffs[s["data_source"]], s["snapshot_at"])

    L = ["# @oli.chases Daily Measurement Brief", "",
         f"- 產生日期：{today}（由 tracker 資料自動產生，`scripts/build_reports.py`）",
         "- 資料涵蓋截止（各來源最新 snapshot_at；來源不合併）："]
    for src, c in sorted(cutoffs.items()):
        L.append(f"  - `{src}`：{c}")
    L += ["", "## 今日新增 / 更新的快照", ""]
    if not today_rows:
        L.append("**今日沒有新快照。** 以下為既有資料的狀態，不是今日更新。")
    else:
        L.append(f"今日新增 {len(today_rows)} 列快照（其中 Graph API {len(today_api)} 列）：")
        for s in today_rows:
            L.append(f"- {s['content_id']}｜age {s['age_hours'] or '—'}h｜reach {s['reach'] or '空'}｜"
                     f"PV {s['profile_visits'] or '空'}｜follows {s['follows'] or '空'}｜{s['data_source']}")
    for l in today_logs:
        if not l["status"].startswith("ok") and l["status"] != "duplicate_skipped":
            L.append(f"- 抓取紀錄：`{l['source']}` {l['content_id']} → {l['status']} {l['error']}".rstrip())
    imports = [l for l in today_logs if l["source"].startswith("import:")]
    if imports:
        L.append(f"- 今日另有 {len(imports)} 筆歷史/人工匯入紀錄（見 fetch_log.csv），匯入的是舊快照，不代表今日新表現。")

    L += ["", "## 各 pillar 最近方向性表現（~24h 快照，最近 60 天發布 vs 全部）", "",
          "| pillar | 近 60 天篇數 | 近期中位 PV/reach | 全部篇數 | 全部中位 PV/reach | 近期中位 follows/reach | 可歸因轉換（近 60 天） | 樣本 |",
          "|---|---|---|---|---|---|---|---|"]
    since = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=60)).strftime("%Y-%m-%d")
    for p in t.PILLARS:
        allr = [s for (cid, b, _), s in best.items() if b == "~24h" and registry[cid]["pillar"] == p]
        rec = [s for s in allr if registry[s["content_id"]]["published_at"][:10] >= since]
        conv_n = sum(sum(attr[s["content_id"]].get(c, 0) for c in FINAL_CONVERSIONS) for s in rec)
        L.append(f"| {p} | {len(rec)} | {pct(med([rates(s)['profile_visits/reach'] for s in rec]))} | {len(allr)} | "
                 f"{pct(med([rates(s)['profile_visits/reach'] for s in allr]))} | "
                 f"{pct(med([rates(s)['follows/reach'] for s in rec]))} | {int(conv_n) if conv_n else ''} | {sample_flag(len(rec))} |")
    L += ["", "follows/reach 空白代表來源沒有 follows 數據，不是 0。", ""]

    L += ["## 可歸因轉換與歸因方式", "", "| conversion_type | attribution_method | 總數 |", "|---|---|---|"]
    agg = defaultdict(float)
    for c in conv:
        agg[(c["conversion_type"], c["attribution_method"])] += num(c["conversion_count"]) or 0
    for (ct, am), n in sorted(agg.items()):
        L.append(f"| {ct} | {am} | {int(n)} |")
    L += ["", "單篇可歸因（direct_utm / manychat_keyword，final conversions）："]
    for cid, d in sorted(attr.items()):
        parts = [f"{k}={int(v)}" for k, v in d.items() if k in FINAL_CONVERSIONS and v]
        if parts:
            L.append(f"- {cid}（{registry.get(cid, {}).get('pillar', '')}）：{', '.join(parts)}")
    L.append("")

    review = [s for s in snaps_all if not s["data_status"].startswith("ok")]
    excluded = t.read_rows(t.EXCLUDED_FILE)
    inferred = sum(1 for r in registry.values() if "pillar_inferred" in r["notes"])
    L += ["## 欄位缺漏、來源差異、樣本不足", "",
          f"- 待確認快照（不進分析）：{len(review)} 列；排除列（測試/內部帳號/他帳號）：{len(excluded)} 列",
          f"- pillar 為推論待確認：{inferred} 篇",
          "- 歷史 Sheet 無 views / follows / non-follower reach / watch time；follows 相關比率目前多為空白",
          "- 2025 舊資料（累計至 2026-04-16）與 2026 MBS 匯出（至 2026-10-24）尚未放入 repo；放入後以獨立 data_source 匯入",
          "- 8/30、9/10 Reel 的 MBS duration（7s / 6s）待人工核實；MBS 時區未證實",
          f"- 每組樣本 < {MIN_N} 一律標記方向性訊號／樣本不足；全部結果皆為描述性，非統計顯著", ""]

    L += ["## 建議 GPT 優先回答的問題", "",
          "1. 哪些內容在 ~24h 的 profile_visits/reach 與 follows/PV 同時偏高？它們的 pillar / CTA 有何共同點？",
          "2. 有可信歸因（direct_utm / manychat_keyword）的轉換來自哪些內容？CTA 文案與關鍵字有何差異？",
          "3. 哪些內容 reach 高但 PV/reach 低（被看見但沒帶到 profile）？是否該調整 hook→profile 的銜接？",
          "4. follows 數據缺口：從 Graph API 開始累積後，哪個 pillar 最先出現穩定的 follows/reach 訊號？",
          "5. 下一篇要測試的單一變因（CTA 類型、關鍵字、格式）是什麼？如何保持其他條件相近以利比較？", ""]
    L += ["## 禁止事項", "",
          "- 不把空白當 0；空白 = 未取得 / 不適用。",
          "- 不混用帳號：@oli.remote.diary、Facebook、合作貼文歸他帳號的數據一律不算 @oli.chases。",
          "- 不把相關性說成因果；樣本小時只稱方向性訊號。",
          "- 不只追 Views / Reach；成功標準是 Follow → Convert。",
          "- 不合併不同來源或不同截止日的數字；不跨 CTA / 觀察期 / 來源比較轉換率。",
          "- 自動更新 ≠ 自動發布或自動改策略；不更動任何已 LOCK 的文案或發文設定。", ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    a = ap.parse_args()
    registry, snaps_all, snaps, conv, log = load()
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(build_report(registry, snaps_all, snaps, conv, a.today))
    with open(BRIEF_FILE, "w", encoding="utf-8") as f:
        f.write(build_brief(registry, snaps_all, snaps, conv, log, a.today))
    print(f"wrote {REPORT_FILE} and {BRIEF_FILE}")


if __name__ == "__main__":
    main()
