# Reports Index

| 日付 | フェーズ | テーマ | 主要結論 | 次アクション | 成果物パス |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-08-15 | フェーズ1 | ベースライン | ドローダウン-57%、取引過多でコスト負け。優位性なし。 | レジーム判定と2段階アーキテクチャの導入 | [`reports/Backtests/01_baseline/baseline_results.png`](01_baseline/baseline_results.png) |
| 2026-08-15 | フェーズ2 | EDA第1弾: SMA/BB | パーフェクトオーダー時は逆張り危険。レンジではBB・SMAがサポレジとして機能。 | stoch_d / AFSの観察へ | [`reports/EDA/01_feature_observation_SMA_BB/report.md`](EDA/01_feature_observation_SMA_BB/report.md) |
| 2026-08-15 | フェーズ2 | EDA第2弾: stoch/AFS | トレンド中は長期AFS張り付き。レンジは全極値到達が反転サイン。ダイバージェンスが転換サイン。 | 2段階アーキテクチャ(v2)の実装・検証へ | [`reports/EDA/02_feature_observation_stoch_AFS/report.md`](EDA/02_feature_observation_stoch_AFS/report.md) |
| 2026-08-15 | フェーズ2 | V2仮説検証 | 取引回数51回、最大DD-6.38%とフィルター機能は有効。しかしリターンは-2.99%でエッジ不足。 | イグジット非依存の定量EDA（エッジマップ作成）へ | [`reports/Backtests/02_hypothesis_verification/report.md`](Backtests/02_hypothesis_verification/report.md) |
| 2026-08-15 | フェーズ3 | EDA第3弾: エッジマップ＆MFE/MAE | 2024年を封印して定量評価。BB_Reversion_Long (勝率60.7%, 24h期待値0.57%)に強いエッジ。トレンド順張りは勝率45%だが期待値微増。 | レジーム別/時期別のエッジ一貫性（非定常）の評価と、MFE/MAEに基づくイグジット設計へ | [`reports/EDA/03_edge_map/report.md`](EDA/03_edge_map/report.md) |
| 2026-08-16 | フェーズ3 | EDA第4弾: 超過エッジ検証 | 【監査済】超過期待値は残るが、クラスタ自己相関を考慮すると95%CIがマイナスを割り込み統計的有意性を喪失。89期間BB反発は単体で有意化せず（局面依存の弱い正兆候）。 | ボラティリティ分位等の未来リークを除去し再集計へ | [`reports/Audits/01_edge_validation_audit/report.md`](Audits/01_edge_validation_audit/report.md) |
| 2026-08-16 | フェーズ3 | 複合シグナル探索(旧) | 【検証済】94試行の複合/独立エッジをTrain(20-21)でFDR補正付き検定した結果、生存候補ゼロ。1時間足・コスト0.2%環境下での堅牢なエッジの不在が証明された。 | 定量特性評価EDAへのピボット | [`reports/Audits/03_composite_search/report.md`](Audits/03_composite_search/report.md) |
| 2026-08-22 | フェーズ3 | EDA第5弾: 定量特性評価(旧期間) | 【参考・旧期間】特徴量とリターンの記述的定量化。Train(2020-2021) | 期間の再設計による再評価へ | [`reports/EDA/05_quantitative_characterization/report_old.md`](EDA/05_quantitative_characterization/report_old.md) |
| 2026-08-22 | フェーズ3 | 期間再設計 (Config更新) | データ量を評価し、Train(2020-2023) / Validation(2024) / Holdout(2025-) に再設計。ハードコードを廃止し `config.py` へ一本化。 | 新期間でのEDA第5弾の再実行へ | N/A |
| 2026-08-22 | フェーズ3 | EDA第5弾: 定量特性評価(新期間) | 【実行済】新Train(2020-2023)の4年間にわたり応答曲線を重ね描きし、2023年まで生き残っている頑健な「関係の形」のみを抽出。 | 特定された構造に基づく厳密な仮説検定の再開へ | [`reports/EDA/05_quantitative_characterization/report.md`](EDA/05_quantitative_characterization/report.md) |
| 2026-08-22 | フェーズ3 | EDA第6弾: 拡張特性評価(MTF・下方リスク) | 【実行済】下方リスク(MAE)はベースラインと大差なく、サポレジ線・順序パターンは非定常で年ごとに反転。1mトリガー(StochGC/BB反発)もGross期待値がほぼゼロで情報価値なし。全拡張テーマを「価値なし(NO)」と厳格に棄却。 | 頑健な構造（EDA05抽出分）のみに絞った厳密な仮説検定へ | [`reports/EDA/06_extended/report.md`](EDA/06_extended/report.md) |
| 2026-08-22 | フェーズ3 | EDA第7弾: レジーム別一貫性の検証(MoE仮説) | 【実行済】非定常な構造をレジーム別（強気/弱気/レンジ×ボラ）に分割して評価。4年間一貫してベースラインを上回る組み合わせは2つのみ（低ボラ弱気×短期急騰、低ボラレンジ×押し目）。しかし純期待値はマイナスの年もあり、「実運用で勝つ」エッジとしては力不足。 | 価格系テクニカル単体からの脱却と次期モデルへの提言 | [`reports/EDA/07_regime/report.md`](EDA/07_regime/report.md) |
