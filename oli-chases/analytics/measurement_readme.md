# @oli.chases Instagram Measurement Tracker

最近更新：2026-10-28

追蹤路徑：**內容 → Profile Visit → Follow → Newsletter / 有效服務詢問 / Workshop 報名 / Purchase**。
核心目標是 **Follow → Convert**。Views、Reach 是診斷指標，不是成功標準。

範圍：只含 Instagram 帳號 @oli.chases（MBS/API 顯示為 `oli_chases`，IG user id `17841431932380351`）。
@oli.remote.diary、Facebook、合作貼文中歸在其他帳號的數據一律不進入本 tracker；cross-post 必須以不同 `platform` / `account` 分列。

## 檔案

| 檔案 | 用途 | 寫入方式 |
|---|---|---|
| `content_registry.csv` | 一篇內容一列 | 匯入/抓取只**新增**未見過的 content_id；既有列（人工標記）不覆寫 |
| `performance_snapshots.csv` | 每次抓取的快照 | 只追加；`(content_id, snapshot_at, data_source)` 重複即跳過 |
| `conversion_events.csv` | 轉換事件（彙總數） | 只追加；完全重複列跳過 |
| `fetch_log.csv` | 每次抓取/匯入的時間、來源、狀態、缺少欄位、失敗原因 | 只追加 |
| `excluded_rows.csv` | 被排除的來源列（測試、內部帳號、他帳號、無法識別）與原因 | 只追加 |
| `daily_measurement_brief.md` | GPT 每日讀取的摘要（自動產生） | 每次覆寫重建 |
| `reports/measurement_report.md` | 完整指標報告（自動產生） | 每次覆寫重建 |
| `sources/` | 已去識別的來源備份與標記表（可提交） | 人工 |
| `raw/` | 原始匯出（MBS、含 email 的 Sheet 匯出）— **gitignored，不提交** | 人工 |
| `scripts/` | 匯入、抓取、報告腳本（Python 3 標準函式庫，無依賴） | — |

## 欄位

**content_registry.csv**
- `content_id`：`ig_<permalink shortcode>`（例：`ig_DdIXHt-x4T7`）。不使用 media id，因 Sheet 中有 media id 被科學記號破壞（`1.79571E+16`）。media id 記在 `notes`。
- `platform` / `account`：`instagram` / `oli.chases`。
- `published_at`：**來源原字串**。Sheet/MBS 的時區未經官方欄位證實，不做轉換；Graph API 抓取的為 UTC ISO。
- `pillar` / `sub_pillar`：見下方字典。`notes` 含 `pillar_inferred` 表示是依文案推論，待人工確認。
- `format`：來源原值（`CAROUSEL_ALBUM`、`REEL`、`VIDEO`、`FEED`、`REELS`…）。
- `cta_type`（`manychat_comment`、`link_in_bio`、`none`…）、`cta_keyword`（例：講座、訂閱）、`utm_campaign`（ManyChat/UTM 的 source_post 值）、`conversion_destination`（`newsletter` / `workshop` / `service` / `product`）。
- `content_status`：`published`、`needs_tagging`、`pending_confirmation`（帳號/來源未確認，不進分析）。

**performance_snapshots.csv**
- `snapshot_at`：抓取時間。Sheet 為原字串；Graph API 為 UTC、取整到小時；MBS 為 `--as-of` 匯出日。
- `age_hours`：snapshot_at − published_at（同一來源的時間字串相減，未做時區轉換）；MBS 累計值為空白。
- 指標欄：`views, reach, non_follower_reach, profile_visits, follows, likes, comments, shares, saves, avg_watch_time, retention_or_skip_rate`。**缺值保留空白，實際 0 才記 0。**
- `data_source`：`gsheet_ig_auto_tracking`、`ig_graph_api`、`mbs_export:<label>`。
- `data_status`：以 `;` 分隔。第一個 token 為 `ok` 才進正式分析；`needs_review:*` 不進分析。其他 token：`sheet_label=1h/24h/final/latest`、`timezone=unverified`、`not_in_source=…`、`unavailable=…`（平台不提供）、`missing=…`、`mbs_duration_sec=…`、`cumulative_as_of_export`。

**conversion_events.csv**
- `event_at`（日期或來源時間字串，來源缺時間則空白）、`content_id`（無法確認則空白）、`conversion_type`、`conversion_count`（彙總數）、`attribution_method`、`utm_campaign`、`notes`。
- 不存 email、姓名、IG 帳號等個資。

## Pillar 字典

| pillar | 說明 | 常用 sub_pillar |
|---|---|---|
| Culture Observation | 台美/歐洲文化差異、社會觀察 | 美國文化、台美教育差異、逆文化衝擊、歐洲生活、職場文化差異 |
| Overseas Workplace Truth | 海外求職與職場現實 | 履歷、面試、海外求職、H-1B、裁員、遠端工作、美國職場文化 |
| Life Insight | 人生選擇與心態 | 人生選擇、生活節奏、心態轉變、情緒管理、成功定義、海外生活心態 |

## 快照規則
- Graph API：發布後 14 天內每次執行都抓；之後在第 21、30、60、90 天各抓一次；超過 95 天不再抓。
- 報告將快照分為 `~1h`（≤3h）、`3-18h`、`~24h`（18–30h）、`2-8d`、`8d+`、`cumulative`（MBS 累計）；只在同一 age bucket、同一來源內比較。
- 不同來源、不同截止日的數字分列保存，不挑一個當真值。

## 轉換類型與歸因

| conversion_type | 定義 |
|---|---|
| `newsletter_signup` | 訂閱 Oli's Notes（ManyChat 收到 email 或 Beehiiv 新增）；ManyChat 來源尚未逐筆比對 Beehiiv 確認 |
| `qualified_inquiry` | 有效服務詢問（履歷/陪跑），人工判定後填入 |
| `workshop_registration` | **確認完成**講座/workshop 報名 |
| `purchase` | 付費購買 |
| `workshop_waitlist` | 漏斗中間步驟：留 email 索取講座連結/候補；**不是報名** |
| `manychat_keyword_trigger` | 漏斗中間步驟：留言關鍵字觸發 ManyChat 但未留 email |

| attribution_method | 意義 | 是否歸給單篇 |
|---|---|---|
| `direct_utm` | ManyChat/UTM 的 source_post 對應到 content_id | 是 |
| `manychat_keyword` | 該貼文留言關鍵字觸發 | 是 |
| `self_reported` | 使用者自述 | 只有指明貼文時填 content_id，報告不計入單篇轉換率 |
| `campaign_level` | 只能歸到 campaign（例：限動、跨多篇） | 否 |
| `time_window` | 發文後時間窗內的新增數（例：Beehiiv 24h 新增） | 否 |
| `unattributed` | 無法歸因 | 否 |

報告中的「X / follows」只用 `direct_utm` + `manychat_keyword`，且只在 follows 有值時計算。

## 資料來源與可取得欄位

| 來源 | 狀態 | 可取得 | 不可取得 / 原因 |
|---|---|---|---|
| Instagram Graph API（`fetch_ig_insights.py`） | 已實作；**需 GitHub Secret `IG_ACCESS_TOKEN` 才會執行** | views、reach、likes、comments、shares、saves；FEED/carousel 的 profile_visits、follows；Reels 的 ig_reels_avg_watch_time。實際可用與否依媒體類型與 API 版本，拒絕的指標記為 `unavailable` | non_follower_reach、retention/skip rate：Graph API 不提供單篇數值，只能從 App/MBS 人工查看 |
| Google Sheet「@oli_chases IG 自動追蹤數據」 | 已備份至 `sources/ig_tracking_sheet_backup_2026-10-28.csv` 並匯入 | reach、likes、comments、saves、shares、profile_visits（部分）、Beehiiv 24h 新增 | views、follows、watch time 從未記錄；4 篇 `final` 列沒有追蹤時間 → `needs_review` |
| Google Sheet「oli.chases Funnel Tracking」（ManyChat/Make） | 已去識別為 `sources/funnel_tracking_extract_2026-10-28.csv` 並彙總 | 每日依 source_post / campaign / CTA 的 lead 數 | Beehiiv 是否確認訂閱；workshop 實際報名 |
| MBS 匯出 | 腳本已備（`import_mbs_export.py`），**檔案尚未放入** | 依匯出欄位 | 時區無官方欄位；8/30、9/10 duration 7s/6s 待核實 |
| `oli_chases_reels_performance.csv` / `oli_chases_reels_snapshots.csv` | **在 repo 與 Google Drive 皆未找到** | — | 放入 `raw/` 後可用 MBS 匯入器或另寫對應 |

Sheet 目前沒有自動同步腳本（同步需要 Google service account）；Graph API 抓取取代 Sheet 作為今後的自動來源。若要再匯入 Sheet 新列：將「貼文數據」分頁下載為 CSV → 存成 `sources/ig_tracking_sheet_backup_<日期>.csv`（刪除「主題摘要」欄）→ 執行匯入（重複列自動跳過）。

## 執行方式

```bash
cd oli-chases/analytics/scripts
python3 import_tracking_sheet.py ../sources/ig_tracking_sheet_backup_2026-10-28.csv
python3 import_funnel_leads.py ../sources/funnel_tracking_extract_2026-10-28.csv   # 或 ../raw/<raw export>.csv
python3 import_mbs_export.py ../raw/<mbs>.csv --as-of 2026-10-24 --label mbs_2026
python3 import_manual_conversions.py ../sources/manual_conversions.csv
IG_ACCESS_TOKEN=... python3 fetch_ig_insights.py
python3 build_reports.py
```

### 人工匯入（UTM 訂閱、ManyChat 觸發、講座報名、詢問、購買）
1. 複製 `sources/manual_conversions_template.csv` 成 `sources/manual_conversions_<日期>.csv`，刪除範例列。
2. 每列一個「日期 × 內容/campaign × 類型」的**彙總數**；無法確認貼文就留空 `content_id` 並用 `campaign_level` / `self_reported` / `unattributed`。
3. `python3 import_manual_conversions.py ../sources/manual_conversions_<日期>.csv`，再 `python3 build_reports.py`。

## 自動排程
`.github/workflows/oli-chases-measurement.yml`：每日 13:17 UTC 及手動觸發。抓取 → 重建報告/brief → 只提交 `oli-chases/analytics/`（若有其他路徑或 `raw/` 變更則拒絕提交）。GitHub 的 schedule 只在 **default branch** 生效。

需要的 GitHub 設定：
- Secret `IG_ACCESS_TOKEN`（必要）：Instagram 專業帳號的長期 token，權限 `instagram_basic` + `instagram_manage_insights`（Facebook Login）或 `instagram_business_basic` + `instagram_business_manage_insights`（Instagram Login）。長期 token 約 60 天到期，需定期更新。
- Secret `IG_USER_ID`（可選，預設 17841431932380351）。
- Variable `IG_GRAPH_HOST`（可選）：用 Instagram Login token 時設為 `graph.instagram.com`。
- Settings → Actions → Workflow permissions 允許 Read and write。

## 限制
- 歷史資料沒有 follows 與 views，因此 follows/reach、轉換/follows 在歷史期間多為空白。
- 所有比較都是描述性；n < 5 標為「方向性訊號／樣本不足」，即使 n ≥ 5 也非統計顯著。
- pillar 標記目前全為推論（`pillar_inferred`），需人工確認。
- `leaving_taiwan_2026715` 對應 `ig_Da1ZK7TkQvP` 是依日期推測（目前該 campaign 只有測試列，未影響數字）。
- ManyChat 的 newsletter lead 尚未與 Beehiiv 實際訂閱逐筆比對。

## GPT 每日讀取
見 `gpt_daily_instructions.md`。
