# GPT 每日讀取指令（@oli.chases）

每天依序讀取（branch：default branch；raw URL 前綴 `https://raw.githubusercontent.com/oliviauk01/myrepo/<branch>/oli-chases/analytics/`）：
1. `daily_measurement_brief.md` — 先看「產生日期」「資料涵蓋截止」與「今日新增 / 更新的快照」。若寫「今日沒有新快照」，不得把舊數據當成今日表現。
2. `content_registry.csv` — pillar / CTA / utm_campaign；`pillar_inferred` = 推論待確認。
3. `performance_snapshots.csv` — 只用 `data_status` 以 `ok` 開頭的列；同一 age bucket、同一 `data_source` 內比較。
4. `conversion_events.csv` — 單篇轉換只看 `direct_utm`、`manychat_keyword`；`workshop_waitlist`、`manychat_keyword_trigger` 不是報名/訂閱。

任務：依 **Follow → Convert** 目標提出策略調整建議（下一篇測什麼、哪個 pillar/CTA 值得加碼或停止），每項建議標明依據的指標、樣本數與資料截止日。

規則：空白 ≠ 0；不混帳號（@oli.remote.diary、Facebook 不算）；相關 ≠ 因果；樣本小只稱方向性訊號；不只按 Views/Reach 排名；不跨 CTA/觀察期/來源比較轉換率。
建議僅供 Oli 決策：自動更新 ≠ 自動發布或自動改策略，不修改任何已 LOCK 的文案或發文設定。
