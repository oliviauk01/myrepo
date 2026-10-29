# @oli.chases Daily Measurement Brief

- 產生日期：2026-10-29（由 tracker 資料自動產生，`scripts/build_reports.py`）
- 資料涵蓋截止（各來源最新 snapshot_at；來源不合併）：
  - `gsheet_ig_auto_tracking`：2026-10-23 12:51

## 今日新增 / 更新的快照

**今日沒有新快照。** 以下為既有資料的狀態，不是今日更新。

## 各 pillar 最近方向性表現（~24h 快照，最近 60 天發布 vs 全部）

| pillar | 近 60 天篇數 | 近期中位 PV/reach | 全部篇數 | 全部中位 PV/reach | 近期中位 follows/reach | 可歸因轉換（近 60 天） | 樣本 |
|---|---|---|---|---|---|---|---|
| Culture Observation | 1 | 1.26% | 5 | 2.17% |  |  | 方向性訊號／樣本不足 |
| Overseas Workplace Truth | 4 | 1.02% | 9 | 1.37% |  | 11 | 方向性訊號／樣本不足 |
| Life Insight | 2 | 2.29% | 3 | 2.89% |  | 1 | 方向性訊號／樣本不足 |

follows/reach 空白代表來源沒有 follows 數據，不是 0。

## 可歸因轉換與歸因方式

| conversion_type | attribution_method | 總數 |
|---|---|---|
| manychat_keyword_trigger | campaign_level | 5 |
| manychat_keyword_trigger | manychat_keyword | 3 |
| newsletter_signup | direct_utm | 8 |
| newsletter_signup | manychat_keyword | 5 |
| newsletter_signup | time_window | 51 |
| workshop_waitlist | campaign_level | 7 |

單篇可歸因（direct_utm / manychat_keyword，final conversions）：
- ig_Db788w4CfDe（Culture Observation）：newsletter_signup=1
- ig_Dcr90R6Dqn7（Overseas Workplace Truth）：newsletter_signup=11
- ig_Dd0TCOAE03B（Life Insight）：newsletter_signup=1

## 欄位缺漏、來源差異、樣本不足

- 待確認快照（不進分析）：6 列；排除列（測試/內部帳號/他帳號）：14 列
- pillar 為推論待確認：28 篇
- 歷史 Sheet 無 views / follows / non-follower reach / watch time；follows 相關比率目前多為空白
- 2025 舊資料（累計至 2026-04-16）與 2026 MBS 匯出（至 2026-10-24）尚未放入 repo；放入後以獨立 data_source 匯入
- 8/30、9/10 Reel 的 MBS duration（7s / 6s）待人工核實；MBS 時區未證實
- 每組樣本 < 5 一律標記方向性訊號／樣本不足；全部結果皆為描述性，非統計顯著

## 建議 GPT 優先回答的問題

1. 哪些內容在 ~24h 的 profile_visits/reach 與 follows/PV 同時偏高？它們的 pillar / CTA 有何共同點？
2. 有可信歸因（direct_utm / manychat_keyword）的轉換來自哪些內容？CTA 文案與關鍵字有何差異？
3. 哪些內容 reach 高但 PV/reach 低（被看見但沒帶到 profile）？是否該調整 hook→profile 的銜接？
4. follows 數據缺口：從 Graph API 開始累積後，哪個 pillar 最先出現穩定的 follows/reach 訊號？
5. 下一篇要測試的單一變因（CTA 類型、關鍵字、格式）是什麼？如何保持其他條件相近以利比較？

## 禁止事項

- 不把空白當 0；空白 = 未取得 / 不適用。
- 不混用帳號：@oli.remote.diary、Facebook、合作貼文歸他帳號的數據一律不算 @oli.chases。
- 不把相關性說成因果；樣本小時只稱方向性訊號。
- 不只追 Views / Reach；成功標準是 Follow → Convert。
- 不合併不同來源或不同截止日的數字；不跨 CTA / 觀察期 / 來源比較轉換率。
- 自動更新 ≠ 自動發布或自動改策略；不更動任何已 LOCK 的文案或發文設定。

