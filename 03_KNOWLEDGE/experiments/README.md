# 実験記録 (Experiments)

本ディレクトリは、Analysis Issue（`#N`）に対応する自己完結型の実験記録ディレクトリ（`<N>-<slug>/`）を格納します。

## ディレクトリ命名規約
```text
<Issue番号>-<短い英小文字スラグ>
例: 20-sma-mean-reversion
    25-htf-squeeze-breakout
```

## 必須構成ファイル
各実験ディレクトリは、単独で再実行可能かつ自己完結していなければなりません。

* `record.md`: 実験の背景、事前登録仮説・判定基準の転記、実行結果、考察
* `config.yaml`: 使用したパラメータおよびデータセット指定
* `run.py`: 再現スクリプト
* `metrics.json`: `02_SPECIFICATIONS/evaluation.md` §4 で定める必須評価メトリクス
* `artifacts/`: 出力されたチャート、グラフ画像
