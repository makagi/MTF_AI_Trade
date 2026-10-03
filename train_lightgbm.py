import os
import numpy as np
import pandas as pd
import lightgbm as lgb
import matplotlib.pyplot as plt
from sklearn.metrics import log_loss, classification_report, accuracy_score, roc_auc_score

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H
from src.labels import get_binary_barrier_labels
from src.ml_utils import PurgedTimeSeriesSplit

def build_v4_5_features(df: pd.DataFrame) -> pd.DataFrame:
    """ v4.5特徴量計算 (Binary Split用ベースライン) """
    df = df.copy()
    features = []
    
    atr = df['ATR_14'].replace(0, np.nan).fillna(method='bfill')
    
    # 1. Macro Alignment Gating
    trend_aligned = np.ones(len(df))
    for k in [9, 10, 11, 12]:
        sma = df[f'FIB_{k}_SMA']
        trend_aligned *= (df['close'] < sma).astype(int)
    df['F_Cascade_Gated'] = trend_aligned
    features.append('F_Cascade_Gated')
    
    # 2. Elasticity Signal
    elasticity = np.zeros(len(df))
    for k in range(2, 12):
        fib_k = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377][k]
        sma_k = df[f'FIB_{k}_SMA']
        sma_prev = df[f'FIB_{k-1}_SMA']
        elasticity += np.log(fib_k) * np.tanh((sma_prev - sma_k) / atr)
    df['F_Elasticity'] = elasticity
    features.append('F_Elasticity')
    
    # 3. Sync Short & Long
    w = 3
    sync_short = np.zeros(len(df))
    short_ks = [3, 4, 5]
    for k in short_ks:
        a_k = df[f'FIB_{k}_stoch_d']
        sync_short += np.tanh((a_k - a_k.shift(w)) / 5.0)
    df['F_Sync_Short'] = sync_short / len(short_ks)
    features.append('F_Sync_Short')
    
    sync_long = np.zeros(len(df))
    long_ks = [10, 11, 12]
    for k in long_ks:
        a_k = df[f'FIB_{k}_stoch_d']
        sync_long += np.tanh((a_k - a_k.shift(w)) / 5.0)
    df['F_Sync_Long'] = sync_long / len(long_ks)
    features.append('F_Sync_Long')
    
    # 4. Macro Gravity Defiance
    df['F_Gravity_Defiance'] = df['F_Sync_Short'] - df['F_Sync_Long']
    features.append('F_Gravity_Defiance')
    
    # 5. Fan-out Velocity
    v_fan = np.zeros(len(df))
    for k in [10, 11, 12]:
        sma_k = df[f'FIB_{k}_SMA']
        sma_next = df[f'FIB_{k+1}_SMA']
        d_k = (sma_k - sma_next) / atr
        v_fan += (d_k - d_k.shift(w))
    df['F_Fanout_Velocity'] = v_fan
    features.append('F_Fanout_Velocity')
    
    # 5.1 Fan-out Acceleration
    df['F_Fanout_Acceleration'] = df['F_Fanout_Velocity'] - df['F_Fanout_Velocity'].shift(1)
    features.append('F_Fanout_Acceleration')
    
    # v4.4 Macro Squeeze
    df['F_Macro_Squeeze'] = -(df['F_Sync_Long'] * df['F_Fanout_Acceleration'])
    features.append('F_Macro_Squeeze')
    
    # 6. Proximity Memory
    df['F_Proximity_Memory'] = df['FIB_11_stoch_d'].ewm(span=24).mean()
    features.append('F_Proximity_Memory')

    # v4.5: Liquidation Flush & Fractal Volatility
    std_144 = df['close'].rolling(144).std().replace(0, np.nan)
    std_21 = df['close'].rolling(21).std().replace(0, np.nan)
    df['F_Fractal_Vol_Spread'] = np.log(std_144 / std_21)
    features.append('F_Fractal_Vol_Spread')
    
    sma_144 = df['FIB_10_SMA']
    bb_upper_144 = sma_144 + 2.0 * std_144
    bb_lower_144 = sma_144 - 2.0 * std_144
    
    df['F_Flush_Depth_L'] = np.maximum(0, (bb_lower_144 - df['low']) / atr)
    df['F_Flush_Depth_S'] = np.maximum(0, (df['high'] - bb_upper_144) / atr)
    features.extend(['F_Flush_Depth_L', 'F_Flush_Depth_S'])
    
    recent_flush_L = df['F_Flush_Depth_L'].rolling(3).max().shift(1)
    recent_flush_S = df['F_Flush_Depth_S'].rolling(3).max().shift(1)
    
    returned_inside_L = (df['close'] > bb_lower_144).astype(int)
    returned_inside_S = (df['close'] < bb_upper_144).astype(int)
    
    exhaustion_L = (df['low'] > df['low'].shift(1)).astype(int)
    exhaustion_S = (df['high'] < df['high'].shift(1)).astype(int)
    
    df['F_Reentry_Trigger_L'] = recent_flush_L * returned_inside_L * exhaustion_L
    df['F_Reentry_Trigger_S'] = recent_flush_S * returned_inside_S * exhaustion_S
    features.extend(['F_Reentry_Trigger_L', 'F_Reentry_Trigger_S'])
    
    df.dropna(subset=features, inplace=True)
    return df, features

def build_v4_6_features(df: pd.DataFrame) -> pd.DataFrame:
    """ v4.6特徴量計算 (Binary Split用ベースライン) """
    df = df.copy()
    features = []
    
    atr = df['ATR_14'].replace(0, np.nan).fillna(method='bfill')
    
    # 1. Cascade Gated
    cascade_raw = np.zeros(len(df))
    for k in range(3, 10):
        a_k = df[f'FIB_{k}_stoch_d']
        a_k_next = df[f'FIB_{k+1}_stoch_d']
        delta = a_k - a_k_next
        cascade_raw += np.tanh(delta / 10.0)
        
    bb_width = df['BB_width_20']
    gate = np.exp(-bb_width / (atr * 2.0))
    df['F_Cascade_Gated'] = cascade_raw * gate
    features.append('F_Cascade_Gated')
    
    # 2. Elasticity Signal
    elasticity = np.zeros(len(df))
    for k in range(2, 12):
        fib_k = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377][k]
        sma_k = df[f'FIB_{k}_SMA']
        sma_prev = df[f'FIB_{k-1}_SMA']
        elasticity += np.log(fib_k) * np.tanh((sma_prev - sma_k) / atr)
    df['F_Elasticity'] = elasticity
    features.append('F_Elasticity')
    
    # 3. Sync Short & Long
    w = 3
    sync_short = np.zeros(len(df))
    short_ks = [3, 4, 5]
    for k in short_ks:
        a_k = df[f'FIB_{k}_stoch_d']
        sync_short += np.tanh((a_k - a_k.shift(w)) / 5.0)
    df['F_Sync_Short'] = sync_short / len(short_ks)
    features.append('F_Sync_Short')
    
    sync_long = np.zeros(len(df))
    long_ks = [10, 11, 12]
    for k in long_ks:
        a_k = df[f'FIB_{k}_stoch_d']
        sync_long += np.tanh((a_k - a_k.shift(w)) / 5.0)
    df['F_Sync_Long'] = sync_long / len(long_ks)
    features.append('F_Sync_Long')
    
    # 4. Macro Gravity Defiance
    df['F_Gravity_Defiance'] = df['F_Sync_Short'] - df['F_Sync_Long']
    features.append('F_Gravity_Defiance')
    
    # 5. Fan-out Velocity
    v_fan = np.zeros(len(df))
    for k in [10, 11, 12]:
        sma_k = df[f'FIB_{k}_SMA']
        sma_next = df[f'FIB_{k+1}_SMA']
        d_k = (sma_k - sma_next) / atr
        v_fan += (d_k - d_k.shift(w))
    df['F_Fanout_Velocity'] = v_fan
    features.append('F_Fanout_Velocity')
    
    # 5.1 Fan-out Acceleration
    df['F_Fanout_Acceleration'] = df['F_Fanout_Velocity'] - df['F_Fanout_Velocity'].shift(1)
    features.append('F_Fanout_Acceleration')
    
    # v4.4 Macro Squeeze
    df['F_Macro_Squeeze'] = -(df['F_Sync_Long'] * df['F_Fanout_Acceleration'])
    features.append('F_Macro_Squeeze')
    
    # 6. Proximity Memory
    df['F_Proximity_Memory'] = df['FIB_11_stoch_d'].ewm(span=24).mean()
    features.append('F_Proximity_Memory')

    # =========================================================================
    # v4.6: Multi-Fibonacci BB (真の大底判定・串刺しスコア)
    # =========================================================================
    fib_ks = [6, 7, 8, 9, 10, 11, 12] # 21, 34, 55, 89, 144, 233, 377
    
    # Calculate all BB layers
    bb_lowers = []
    bb_uppers = []
    
    for k in fib_ks:
        period = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377][k]
        std = df['close'].rolling(period, min_periods=1).std().bfill()
        sma = df[f'FIB_{k}_SMA']
        bb_lower = sma - 2.0 * std
        bb_upper = sma + 2.0 * std
        
        df[f'FIB_{k}_BB_lower'] = bb_lower
        df[f'FIB_{k}_BB_upper'] = bb_upper
        
        bb_lowers.append(df[f'FIB_{k}_BB_lower'])
        bb_uppers.append(df[f'FIB_{k}_BB_upper'])
        
    bb_lower_max = pd.concat(bb_lowers, axis=1).max(axis=1)
    bb_lower_min = pd.concat(bb_lowers, axis=1).min(axis=1)
    df['F_BB_Lower_Thickness'] = (bb_lower_max - bb_lower_min) / atr
    
    bb_upper_max = pd.concat(bb_uppers, axis=1).max(axis=1)
    bb_upper_min = pd.concat(bb_uppers, axis=1).min(axis=1)
    df['F_BB_Upper_Thickness'] = (bb_upper_max - bb_upper_min) / atr
    features.extend(['F_BB_Lower_Thickness', 'F_BB_Upper_Thickness'])
    
    # Penetration Score (0 to 7)
    df['F_Penetration_Score_L'] = sum((df['low'] < df[f'FIB_{k}_BB_lower']).astype(int) for k in fib_ks)
    df['F_Penetration_Score_S'] = sum((df['high'] > df[f'FIB_{k}_BB_upper']).astype(int) for k in fib_ks)
    features.extend(['F_Penetration_Score_L', 'F_Penetration_Score_S'])
    
    # Re-entry Trigger v2 (究極の狙撃トリガー)
    recent_panic_L = df['F_Penetration_Score_L'].rolling(3).max().shift(1).fillna(0)
    recent_panic_S = df['F_Penetration_Score_S'].rolling(3).max().shift(1).fillna(0)
    
    full_return_L = (df['close'] > bb_lower_max).astype(int)
    full_return_S = (df['close'] < bb_upper_min).astype(int)
    
    exhaustion_L = (df['low'] > df['low'].shift(1)).astype(int)
    exhaustion_S = (df['high'] < df['high'].shift(1)).astype(int)
    
    df['F_Reentry_Trigger_v2_L'] = np.where(recent_panic_L >= 5, recent_panic_L * full_return_L * exhaustion_L, 0)
    df['F_Reentry_Trigger_v2_S'] = np.where(recent_panic_S >= 5, recent_panic_S * full_return_S * exhaustion_S, 0)
    features.extend(['F_Reentry_Trigger_v2_L', 'F_Reentry_Trigger_v2_S'])
    
    df.dropna(subset=features, inplace=True)
    return df, features

def train_binary_model(df, feature_cols, direction, pt_sl_ratio, time_barrier=24, version="v4_6"):
    print(f"\n=========================================")
    print(f"Training {direction.upper()} Model (PT={pt_sl_ratio[0]}, SL={pt_sl_ratio[1]}, TB={time_barrier})")
    print(f"=========================================")
    
    tb_df = get_binary_barrier_labels(
        df, 
        pt_sl_ratio=pt_sl_ratio, 
        time_barrier=time_barrier,
        direction=direction,
        atr_col='ATR_14'
    )
    
    train_data = df.copy()
    train_data['label'] = tb_df['label']
    
    train_data.dropna(subset=['label'] + feature_cols, inplace=True)
    
    y = train_data['label']
    X = train_data[feature_cols]
    
    print(f"Class distribution for {direction.upper()}:")
    print(y.value_counts(normalize=True))
    
    cv = PurgedTimeSeriesSplit(n_splits=5, purge_period=24)
    
    params = {
        'objective': 'binary',
        'metric': 'binary_logloss',
        'boosting_type': 'gbdt',
        'max_depth': 3,
        'min_data_in_leaf': 100,
        'learning_rate': 0.05,
        'colsample_bytree': 0.7,
        'lambda_l1': 1.0,
        'lambda_l2': 1.0,
        'random_state': 42,
        'n_estimators': 200,
        'verbose': -1
    }
    
    fold_scores = []
    fold_aucs = []
    feature_importances = np.zeros(len(feature_cols))
    
    for fold, (train_idx, val_idx) in enumerate(cv.split(X)):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_val, y_val = X.iloc[val_idx], y.iloc[val_idx]
        
        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)]
        )
        
        preds = model.predict_proba(X_val)[:, 1]
        score = log_loss(y_val, preds)
        auc = roc_auc_score(y_val, preds)
        
        fold_scores.append(score)
        fold_aucs.append(auc)
        feature_importances += model.feature_importances_ / cv.get_n_splits()
        
        print(f"Fold {fold}: Log Loss = {score:.4f}, AUC = {auc:.4f}")
        
    print(f"\nAverage CV Log Loss: {np.mean(fold_scores):.4f}")
    print(f"Average CV AUC: {np.mean(fold_aucs):.4f}")
    
    print("Retraining on full dataset for final model...")
    final_model = lgb.LGBMClassifier(**params)
    final_model.fit(X, y)
    
    model_path = f"models/lgbm_{version}_{direction}.txt"
    os.makedirs("models", exist_ok=True)
    final_model.booster_.save_model(model_path)
    print(f"Saved model to {model_path}")
    
    importance_df = pd.DataFrame({
        'Feature': feature_cols,
        'Importance': feature_importances
    }).sort_values(by='Importance', ascending=False)
    
    os.makedirs("results", exist_ok=True)
    plt.figure(figsize=(10, 6))
    plt.barh(importance_df['Feature'][::-1], importance_df['Importance'][::-1])
    plt.title(f"LightGBM Feature Importance ({direction.upper()})")
    plt.xlabel("Average Split Importance")
    plt.tight_layout()
    plt.savefig(f"results/lgbm_{version}_importance_{direction}.png")
    plt.close()

def build_v4_7_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """ v4.7 Master Plan Features """
    df = df.copy()
    features = []
    
    fib_ks = [6, 7, 8, 9, 10, 11, 12] # 21, 34, 55, 89, 144, 233, 377
    atr = df['ATR_14'].replace(0, np.nan).fillna(method='bfill')
    epsilon = 1e-8
    
    bb_lowers = []
    bb_uppers = []
    
    for k in fib_ks:
        period = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377][k]
        std = df['close'].rolling(period, min_periods=1).std().bfill()
        sma = df[f'FIB_{k}_SMA']
        
        lower = sma - 2.0 * std
        upper = sma + 2.0 * std
        
        df[f'FIB_{k}_BB_lower'] = lower
        df[f'FIB_{k}_BB_upper'] = upper
        
        bb_lowers.append(lower)
        bb_uppers.append(upper)
    
    bb_lower_min = pd.concat(bb_lowers, axis=1).min(axis=1)
    bb_lower_max = pd.concat(bb_lowers, axis=1).max(axis=1)
    
    bb_upper_max = pd.concat(bb_uppers, axis=1).max(axis=1)
    bb_upper_min = pd.concat(bb_uppers, axis=1).min(axis=1)

    # 1. Proximity
    df['F_Floor_Proximity'] = (df['close'] - bb_lower_min) / (bb_lower_max - bb_lower_min + epsilon)
    df['F_Ceiling_Proximity'] = (bb_upper_max - df['close']) / (bb_upper_max - bb_upper_min + epsilon)
    
    # 2. Traction (21 vs 55)
    df['F_Traction_L'] = (df['FIB_6_BB_lower'] - df['FIB_8_BB_lower']) / atr
    df['F_Traction_S'] = (df['FIB_6_BB_upper'] - df['FIB_8_BB_upper']) / atr
    
    # 3. Wave Propagation (Weighted Z-scores)
    wave_L = np.zeros(len(df))
    wave_S = np.zeros(len(df))
    weights = [0.40, 0.25, 0.15, 0.10, 0.05, 0.03, 0.02] 
    
    for i, k in enumerate(fib_ks):
        mom_L = df[f'FIB_{k}_BB_lower'].diff(1)
        z_L = mom_L / (mom_L.rolling(100).std() + epsilon)
        wave_L += z_L.clip(-3, 3) * weights[i]
        
        mom_S = df[f'FIB_{k}_BB_upper'].diff(1)
        z_S = mom_S / (mom_S.rolling(100).std() + epsilon)
        wave_S += z_S.clip(-3, 3) * weights[i]
        
    df['F_Wave_Propagation_L'] = wave_L
    df['F_Wave_Propagation_S'] = wave_S
    
    # Optional: Keep some base features for the model to understand context
    df['F_ATR_Ratio'] = atr / df['close']
    
    features.extend([
        'F_Floor_Proximity', 'F_Ceiling_Proximity', 
        'F_Traction_L', 'F_Traction_S', 
        'F_Wave_Propagation_L', 'F_Wave_Propagation_S',
        'F_ATR_Ratio'
    ])

    # 4. Triggers
    recent_floor = df['F_Floor_Proximity'].rolling(24).min() < 0.2
    recent_ceiling = df['F_Ceiling_Proximity'].rolling(24).min() < 0.2
    
    traction_cross_L = (df['F_Traction_L'] > 0) & (df['F_Traction_L'].shift(1) <= 0)
    traction_cross_S = (df['F_Traction_S'] < 0) & (df['F_Traction_S'].shift(1) >= 0)
    
    df['F_Trigger_v3_L'] = (recent_floor & traction_cross_L).astype(int)
    df['F_Trigger_v3_S'] = (recent_ceiling & traction_cross_S).astype(int)
    features.extend(['F_Trigger_v3_L', 'F_Trigger_v3_S'])
    
    df.dropna(subset=features, inplace=True)
    return df, features

def build_v5_0_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """ v5.0 Zero-Lag Macro Sniper """
    df = df.copy()
    features = []
    
    fib_ks = [6, 7, 8, 9, 10, 11, 12] # 21, 34, 55, 89, 144, 233, 377
    epsilon = 1e-8
    
    bb_lowers = []
    bb_uppers = []
    
    for k in fib_ks:
        period = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377][k]
        std = df['close'].rolling(period, min_periods=1).std().bfill()
        sma = df[f'FIB_{k}_SMA']
        lower = sma - 2.0 * std
        upper = sma + 2.0 * std
        df[f'FIB_{k}_BB_lower'] = lower
        df[f'FIB_{k}_BB_upper'] = upper
        bb_lowers.append(lower)
        bb_uppers.append(upper)
    
    bb_lower_min = pd.concat(bb_lowers, axis=1).min(axis=1)
    bb_lower_max = pd.concat(bb_lowers, axis=1).max(axis=1)
    bb_upper_max = pd.concat(bb_uppers, axis=1).max(axis=1)
    bb_upper_min = pd.concat(bb_uppers, axis=1).min(axis=1)

    df['F_Floor_Proximity'] = (df['close'] - bb_lower_min) / (bb_lower_max - bb_lower_min + epsilon)
    df['F_Ceiling_Proximity'] = (bb_upper_max - df['close']) / (bb_upper_max - bb_upper_min + epsilon)
    
    # Wave Propagation (Weighted Z-scores)
    wave_L = np.zeros(len(df))
    wave_S = np.zeros(len(df))
    weights = [0.40, 0.25, 0.15, 0.10, 0.05, 0.03, 0.02] 
    
    for i, k in enumerate(fib_ks):
        mom_L = df[f'FIB_{k}_BB_lower'].diff(1)
        z_L = mom_L / (mom_L.rolling(100).std() + epsilon)
        wave_L += z_L.clip(-3, 3) * weights[i]
        
        mom_S = df[f'FIB_{k}_BB_upper'].diff(1)
        z_S = mom_S / (mom_S.rolling(100).std() + epsilon)
        wave_S += z_S.clip(-3, 3) * weights[i]
        
    df['F_Wave_Propagation_L'] = wave_L
    df['F_Wave_Propagation_S'] = wave_S

    # ML features
    df['F_ATR_Ratio'] = df['ATR_14'].replace(0, np.nan).fillna(method='bfill') / df['close']
    df['F_Macro_Micro_Ratio'] = df['FIB_10_SMA'] / df['FIB_6_SMA']
    features.extend(['F_Floor_Proximity', 'F_Ceiling_Proximity', 'F_Wave_Propagation_L', 'F_Wave_Propagation_S', 'F_ATR_Ratio', 'F_Macro_Micro_Ratio'])

    # Add Macro Oscillator features for ML to learn the TN vs FN difference
    features.extend(['FIB_13_stoch_d_slope', 'AFS_10_19', 'FIB_15_BB_pos', 'FIB_14_BB_pos'])
    
    # Triggers (v5.0 Macro Sniper: relaxed burnout + ML macro filtering)
    recent_floor = df['F_Floor_Proximity'].rolling(72).min() < 0.1
    recent_ceiling = df['F_Ceiling_Proximity'].rolling(72).min() < 0.1
    
    macro_despair_L = df['FIB_10_BB_lower'].diff(1) < 0
    macro_euphoria_S = df['FIB_10_BB_upper'].diff(1) > 0
    
    micro_vel_L = df['FIB_6_BB_lower'].diff(1)
    micro_vel_S = df['FIB_6_BB_upper'].diff(1)
    micro_reversal_L = (micro_vel_L > 0) & (micro_vel_L.shift(1) <= 0)
    micro_reversal_S = (micro_vel_S < 0) & (micro_vel_S.shift(1) >= 0)
    
    # Relaxed Burnout filter (to allow 21-BB lag), ML will filter knives
    burnout_safe_L = df['F_Floor_Proximity'] < 0.85
    burnout_safe_S = df['F_Ceiling_Proximity'] < 0.85
    
    # Strict point-in-time wave check filters out false bottoms
    wave_despair_L = df['F_Wave_Propagation_L'] < -0.50
    wave_euphoria_S = (df['F_Wave_Propagation_S'] > 0.0) & (df['F_Wave_Propagation_S'] < 1.0)
    
    # Engine 1: Absolute Bottom Sniper
    df['F_Trigger_v5_L'] = (recent_floor & macro_despair_L & micro_reversal_L & burnout_safe_L & wave_despair_L).astype(int)
    df['F_Trigger_v5_S'] = (recent_ceiling & macro_euphoria_S & micro_reversal_S & burnout_safe_S & wave_euphoria_S).astype(int)
    
    # Engine 2: Trend Pullback Trigger
    macro_uptrend_L = (df['FIB_9_SMA'] > df['FIB_10_SMA']) & (df['FIB_10_SMA'] > df['FIB_11_SMA'])
    macro_downtrend_S = (df['FIB_9_SMA'] < df['FIB_10_SMA']) & (df['FIB_10_SMA'] < df['FIB_11_SMA'])
    
    mid_dip_L = df['low'] <= df['FIB_7_BB_lower'] # 21 BB touch (more common shallow dip)
    mid_dip_S = df['high'] >= df['FIB_7_BB_upper']
    
    local_panic_L = df['F_Wave_Propagation_L'] < 0.0 # Any local negative momentum
    local_panic_S = df['F_Wave_Propagation_S'] > 0.0
    
    trigger_hook_L = df['FIB_9_stoch_d_slope'] > 0
    trigger_hook_S = df['FIB_9_stoch_d_slope'] < 0
    # The MTF 1m logic will handle the exact timing (Time Delta > 30m)
    # So we don't need a lagging 1h stochastic hook!
    df['F_Trigger_Trend_L'] = (macro_uptrend_L & mid_dip_L & local_panic_L).astype(int)
    df['F_Trigger_Trend_S'] = (macro_downtrend_S & mid_dip_S & local_panic_S).astype(int)
    
    features.extend(['F_Trigger_v5_L', 'F_Trigger_v5_S'])
    df.dropna(subset=features, inplace=True)
    return df, features

def run():
    print("Loading data...")
    df = load_1h_data(include_holdout=False)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    
    print("Building v5.0 features...")
    df, feature_cols = build_v5_0_features(df)
    
    # Asymmetric Barriers
    train_binary_model(df, feature_cols, direction='long', pt_sl_ratio=[2.5, 1.0], time_barrier=72, version="v5_0")
    train_binary_model(df, feature_cols, direction='short', pt_sl_ratio=[1.5, 1.0], time_barrier=72, version="v5_0")

if __name__ == "__main__":
    run()
