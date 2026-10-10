# 複合シグナル探索フェーズ (Pre-registered Search)

- [x] 1. `src/eda_composite_search.py` の実装
  - [x] Train(20-21) / Val(22-23) の厳密な分離と一方向フローの構築
  - [x] 探索空間（全94試行）の定義（BBゲーティング90 + 独立エッジ4）
  - [x] 全94試行のp値に対するFDR（Benjamini-Hochberg）補正の実装
  - [x] Gate A (Train選抜) と Gate B (Val一発勝負) の合否判定ロジック
  - [x] フォールバック対照群イベント数のカウントと記録
- [x] 2. 探索の実行とレポートの出力
  - [x] Train全セル一覧、FDR生存候補、Val判定結果のCSV出力
  - [x] 年×レジーム別内訳CSV出力 (※候補0のためTrain全件出力に代替)
- [x] 3. INDEX.md および STATE.md の更新
- [x] 4. 結果の報告（第8章形式）
