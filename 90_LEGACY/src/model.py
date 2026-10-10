import numpy as np
import pandas as pd
import lightgbm as lgb
import warnings
warnings.filterwarnings('ignore')

def create_target(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """N期間後のリターンを目的変数として作成"""
    df = df.copy()
    # N期間先の終値
    df['future_close'] = df['close'].shift(-horizon)
    # リターン
    df['target_return'] = (df['future_close'] - df['close']) / df['close']
    # 分類用ラベル: リターンが正なら1、負なら0
    df['target_label'] = (df['target_return'] > 0).astype(int)
    
    # NAを落とす
    df.dropna(subset=['target_return'], inplace=True)
    return df

def train_lightgbm_baseline(df: pd.DataFrame, feature_cols: list):
    """
    ベースラインのLightGBM分類器を学習する。
    時系列で Train (70%), Val (15%), Test (15%) に分割してWalk-Forwardの簡易版とする。
    """
    # 欠損値を含む行を削除（特徴量計算初期など）
    df = df.dropna(subset=feature_cols)
    
    n = len(df)
    train_end = int(n * 0.7)
    val_end = int(n * 0.85)
    
    train_df = df.iloc[:train_end]
    val_df = df.iloc[train_end:val_end]
    test_df = df.iloc[val_end:]
    
    X_train = train_df[feature_cols]
    y_train = train_df['target_label']
    
    X_val = val_df[feature_cols]
    y_val = val_df['target_label']
    
    X_test = test_df[feature_cols]
    y_test = test_df['target_label']
    
    # 複雑すぎるモデルは過学習を招くため、ハイパーパラメータはシンプルに
    params = {
        'n_estimators': 200,
        'learning_rate': 0.05,
        'max_depth': 4,
        'random_state': 42,
        'importance_type': 'gain'
    }
    
    model = lgb.LGBMClassifier(**params)
    
    # Early stopping
    callbacks = [lgb.early_stopping(stopping_rounds=20, verbose=False)]
    
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=callbacks
    )
    
    # 予測確率 (Longの確率)
    test_preds = model.predict_proba(X_test)[:, 1]
    
    return model, test_df, test_preds, train_df, val_df
