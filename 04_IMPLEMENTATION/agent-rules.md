# AIエージェント行動規範 (Agent Rules)

**Doc ID:** RULE-AGT-001  
**Version:** 0.1.0  
**Status:** Draft  
**Owner:** @makagi  
**Last Updated:** 2026-10-10  
**Related Issues:** [#4](https://github.com/makagi/MTF_AI_Trade/issues/4)  
**Related Docs:** [00_GOVERNANCE/issue-driven-workflow.md](../00_GOVERNANCE/issue-driven-workflow.md), [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md)  

---

## 1. 禁止事項 (Strictly Prohibited)

1. **仕様の無断変更禁止 (No Unilateral Spec Changes)**:
   - `00_GOVERNANCE/`、`01_CONCEPTS/`、`02_SPECIFICATIONS/` の内容を、人間の明示的な合意（PR マージ）なしに直接変更してはならない。自己承認による PR マージも厳禁。
2. **未検証アイデアの「確定事実化」禁止**:
   - バックテストや統計検定を経ていないアイデアを「エッジがある」「有効である」と断定してドキュメントやコードに組み込んではならない。必ず「仮説（Hypothesis）」として扱うこと。
3. **最終ホールドアウト期間へのアクセス禁止**:
   - [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) §2.3 で定義する Final Holdout 期間のデータは、いかなる探索・チューニング・中間バックテストでもアクセスしてはならない。
4. **チェリーピッキング・都合の良い結果のみの報告禁止**:
   - 特定の年や相場でのみ勝てた結果を誇張し、トータルで負けている結果やドローダウンを隠蔽してはならない。事前登録した判定基準（Analysis Issue）に忠実に評価すること。
5. **「方針」と「仕様」の混在禁止**:
   - 普遍的な相場概念（Concept）と個別パラメータ（Specification）を同一箇所に記述してはならない。

---

## 2. 必須行動 (Mandatory Actions)

1. **変更理由と系譜の記録**:
   - コードや特徴量の計算ロジックを変更する際は、必ず「どの仮説・実験・決定に基づく変更か」をコミットメッセージや PR に明記する。
2. **定量的根拠の提示**:
   - 改善を主張する場合、必ず [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) §4 で規定する必須評価メトリクス（サンプル数、摩擦コスト控除後期待値、年別・レジーム別分解、MFE/MAE、Max DD）を提示すること。
3. **既存コード・ドキュメントの整合性保持**:
   - 既存のコメント、ドキュメント構造、および確立された命名規則を尊重し、不要な破壊的変更を行わない。
4. **再現性の担保**:
   - 実行したスクリプト名、引数、シード値、データセットハッシュ、出力ログを正確に記録すること。
