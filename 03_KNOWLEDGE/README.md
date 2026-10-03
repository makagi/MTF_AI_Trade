# 知識・仮説・実験管理 (03_KNOWLEDGE)

本ディレクトリは、プロジェクトにおける仮説（Hypothesis）、実験設定と結果（Experiment）、および既存の分析レコード（Analysis Record: [knowledge/records/](file:///d:/work/AI-Trade/MTF_AI_Trade/knowledge/records/)）と知識の系譜（Knowledge Lineage）を管理します。

---

## 1. サブディレクトリ構成

```text
03_KNOWLEDGE/
├── hypotheses/             # 仮説レジストリ (H001, H002...)
│   └── README.md
├── experiments/            # バックテスト・実験ログ (E001, E002...)
│   └── README.md
├── analyses/               # knowledge/records/ への参照・インデックス
└── knowledge-lineage.md    # 知識の系譜 (仮説→実験→知識の因果関係)
```

---

## 2. ライフサイクル

```text
[仮説立案]  03_KNOWLEDGE/hypotheses/HXXX.md (Status: Testing)
   ↓
[実験実行]  03_KNOWLEDGE/experiments/EXXX.md (パラメータ・結果ログ)
   ↓
[エビデンス] 03_KNOWLEDGE/knowledge-lineage.md に因果関係を記録
   ↓
[採否判定]  Supported → 02_SPECIFICATIONS に反映 / Refuted → 棄却理由を記録
```
