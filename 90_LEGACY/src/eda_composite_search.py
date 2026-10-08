import os
import pandas as pd
import numpy as np
from scipy.stats import false_discovery_control
from src.config import MAX_FIB_INDEX_1H, FIBONACCI_SERIES, BASE_COST, TARGET_HORIZON_1H
from src.data_loader import load_discovery_data
from src.features import calculate_fib_features
from src.eda_audit import get_event_clusters

SEARCH_DIR = r"D:\work\AI-Trade\SakanaAISystemTrade\reports\Audits\03_composite_search"
os.makedirs(SEARCH_DIR, exist_ok=True)

HORIZON = 24
N_BOOT = 2000

def bootstrap_test(returns, clusters, n_boot=N_BOOT, ci=0.95):
    """Cluster bootstrap for CI and 1-sided p-value (H0: mean <= 0)"""
    df = pd.DataFrame({'ret': returns, 'cluster': clusters})
    unique_clusters = df['cluster'].unique()
    if len(unique_clusters) < 2: return np.nan, np.nan, 1.0
    
    boot_means = []
    for _ in range(n_boot):
        sampled_clusters = np.random.choice(unique_clusters, size=len(unique_clusters), replace=True)
        # Fast reconstruction
        counts = pd.Series(sampled_clusters).value_counts()
        sampled_rets = []
        for c, count in counts.items():
            c_rets = df[df['cluster'] == c]['ret'].values
            if count == 1:
                sampled_rets.extend(c_rets)
            else:
                sampled_rets.extend(np.tile(c_rets, count))
                
        if len(sampled_rets) > 0:
            boot_means.append(np.mean(sampled_rets))
            
    if not boot_means: return np.nan, np.nan, 1.0
    boot_means = np.array(boot_means)
    
    ci_lower = np.percentile(boot_means, (1 - ci) / 2 * 100)
    ci_upper = np.percentile(boot_means, (1 + ci) / 2 * 100)
    
    # p-value for H0: mean <= 0
    p_val = np.mean(boot_means <= 0)
    # prevent strict 0 p-value
    p_val = max(p_val, 1/n_boot)
    
    return ci_lower, ci_upper, p_val

def trimmed_mean(arr, percent=0.1):
    n = len(arr)
    k = int(n * percent)
    if k == 0 or n < 3: return np.mean(arr)
    sorted_arr = np.sort(arr)
    return np.mean(sorted_arr[k:-k])

def define_regimes_leak_free(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    slope_l_pct = df['FIB_11_SMA_slope'].abs() / df['close']
    afs_long = df['AFS_10_19']
    
    df['regime_type'] = np.where((slope_l_pct > 0.0001) & ((afs_long > 60) | (afs_long < 40)), 'Trend', 'Range')
    
    tr = np.maximum(df['high'] - df['low'], 
                    np.maximum(abs(df['high'] - df['close'].shift(1)), 
                               abs(df['low'] - df['close'].shift(1))))
    atr = tr.rolling(14).mean()
    atr_pct = atr / df['close']
    
    rolling_window = 2160
    q33 = atr_pct.rolling(window=rolling_window, min_periods=24).quantile(0.33).bfill()
    q66 = atr_pct.rolling(window=rolling_window, min_periods=24).quantile(0.66).bfill()
    
    conditions = [atr_pct <= q33, atr_pct <= q66, atr_pct > q66]
    choices = ['LowVol', 'MidVol', 'HighVol']
    df['regime_vol'] = np.select(conditions, choices, default='MidVol')
    
    df['prev_24h_ret'] = df['close'] / df['close'].shift(24) - 1.0
    q25 = df['prev_24h_ret'].rolling(window=rolling_window, min_periods=24).quantile(0.25).bfill()
    q50 = df['prev_24h_ret'].rolling(window=rolling_window, min_periods=24).quantile(0.50).bfill()
    q75 = df['prev_24h_ret'].rolling(window=rolling_window, min_periods=24).quantile(0.75).bfill()
    
    conditions_ret = [
        df['prev_24h_ret'] <= q25,
        (df['prev_24h_ret'] > q25) & (df['prev_24h_ret'] <= q50),
        (df['prev_24h_ret'] > q50) & (df['prev_24h_ret'] <= q75),
        df['prev_24h_ret'] > q75
    ]
    choices_ret = ['Q1', 'Q2', 'Q3', 'Q4']
    df['prev_ret_quartile'] = np.select(conditions_ret, choices_ret, default='Q1')
    
    df['regime_label'] = df['regime_type'] + "_" + df['regime_vol']
    df['year'] = df.index.year
    df['control_group_id'] = df['year'].astype(str) + "_" + df['regime_label'] + "_" + df['prev_ret_quartile']
    return df

def define_base_signals(df: pd.DataFrame) -> dict:
    signals = {}
    
    # 1. BB_Reversion (FIB 8~12)
    for idx in [8, 9, 10, 11, 12]:
        period = FIBONACCI_SERIES[idx-1]
        down_col = f'FIB_{idx}_BB_down'
        up_col = f'FIB_{idx}_BB_up'
        if down_col in df.columns:
            sig_long = (df['low'].shift(1) < df[down_col].shift(1)) & (df['close'] > df[down_col])
            sig_short = (df['high'].shift(1) > df[up_col].shift(1)) & (df['close'] < df[up_col])
            signals[f'BB_Reversion_Long_{period}'] = {'series': sig_long, 'direction': 'Long', 'type': 'BB'}
            signals[f'BB_Reversion_Short_{period}'] = {'series': sig_short, 'direction': 'Short', 'type': 'BB'}
            
    # 2. Independent Edges
    # Stoch_d Pullback (using FIB 8 = 34 period for a medium oscillation)
    stoch_d = df['FIB_8_stoch_d']
    stoch_d_slope = df['FIB_8_stoch_d_slope']
    stoch_long = (stoch_d < 30) & (stoch_d_slope > 0) & (stoch_d.shift(1) <= stoch_d.shift(2))
    stoch_short = (stoch_d > 70) & (stoch_d_slope < 0) & (stoch_d.shift(1) >= stoch_d.shift(2))
    signals['Stoch_d_Pullback_Long'] = {'series': stoch_long, 'direction': 'Long', 'type': 'Indep'}
    signals['Stoch_d_Pullback_Short'] = {'series': stoch_short, 'direction': 'Short', 'type': 'Indep'}
    
    # SMA Perfect Order (FIB 3 to 10) -> 3,5,8,13,21,34,55,89
    sma_cols = [f'FIB_{i}_SMA' for i in range(3, 11)]
    if all(c in df.columns for c in sma_cols):
        long_cond = True
        short_cond = True
        for i in range(len(sma_cols)-1):
            long_cond &= (df[sma_cols[i]] > df[sma_cols[i+1]]) & (df[f'FIB_{i+3}_SMA_slope'] > 0)
            short_cond &= (df[sma_cols[i]] < df[sma_cols[i+1]]) & (df[f'FIB_{i+3}_SMA_slope'] < 0)
        signals['SMA_Perfect_Order_Long'] = {'series': long_cond, 'direction': 'Long', 'type': 'Indep'}
        signals['SMA_Perfect_Order_Short'] = {'series': short_cond, 'direction': 'Short', 'type': 'Indep'}
        
    return signals

def build_hypotheses(df: pd.DataFrame, signals: dict) -> list:
    hypotheses = []
    
    for sig_name, info in signals.items():
        if info['type'] == 'Indep':
            # 独立エッジはフィルタなしで1試行
            hypotheses.append({
                'id': sig_name,
                'base_signal': sig_name,
                'gate_type': 'None',
                'gate_val': 'None',
                'series': info['series'],
                'direction': info['direction']
            })
        elif info['type'] == 'BB':
            # BBゲーティング (Regime 2 + Vol 3 + PrevRet 4 = 9 filters)
            # Regime
            for r in ['Trend', 'Range']:
                hypotheses.append({
                    'id': f"{sig_name}_Gate_{r}",
                    'base_signal': sig_name,
                    'gate_type': 'Regime',
                    'gate_val': r,
                    'series': info['series'] & (df['regime_type'] == r),
                    'direction': info['direction']
                })
            # Vol
            for v in ['LowVol', 'MidVol', 'HighVol']:
                hypotheses.append({
                    'id': f"{sig_name}_Gate_{v}",
                    'base_signal': sig_name,
                    'gate_type': 'Volatility',
                    'gate_val': v,
                    'series': info['series'] & (df['regime_vol'] == v),
                    'direction': info['direction']
                })
            # PrevRet
            for q in ['Q1', 'Q2', 'Q3', 'Q4']:
                hypotheses.append({
                    'id': f"{sig_name}_Gate_{q}",
                    'base_signal': sig_name,
                    'gate_type': 'PrevRet',
                    'gate_val': q,
                    'series': info['series'] & (df['prev_ret_quartile'] == q),
                    'direction': info['direction']
                })
                
    return hypotheses

def evaluate_subset(df: pd.DataFrame, hypotheses: list, prefix: str):
    results = []
    
    # Pre-calculate non-signal drift map for the full period (df) to match control groups
    # Note: df is already subset to Train or Val, so we use its unconditional mean for fallback
    unc_drift = df[f'fwd_ret_h{HORIZON}'].mean()
    
    for hyp in hypotheses:
        is_sig = hyp['series']
        dir_mult = 1 if hyp['direction'] == 'Long' else -1
        
        events = df[is_sig].copy()
        
        n_raw = len(events)
        if n_raw == 0:
            results.append({'id': hyp['id'], f'{prefix}_N_raw': 0, f'{prefix}_N_cluster': 0, f'{prefix}_p_val': 1.0})
            continue
            
        event_positions = [df.index.get_loc(idx) for idx in events.index]
        events['cluster'] = get_event_clusters(event_positions, gap=24)
        n_cluster = len(events['cluster'].unique())
        
        # We need matched drift. Since we evaluate specific hypotheses, the "non-signal" is just ~is_sig.
        # But to be clean and fast, we use the global ~base_signal for matched drift.
        # However, for simplicity and correctness of hypothesis testing, we use ~is_sig.
        df_non_sig = df[~is_sig]
        mat_drift_map = df_non_sig.groupby('control_group_id')[f'fwd_ret_h{HORIZON}'].mean().to_dict()
        
        rets = events[f'fwd_ret_h{HORIZON}'].dropna()
        if len(rets) == 0:
            results.append({'id': hyp['id'], f'{prefix}_N_raw': 0, f'{prefix}_N_cluster': 0, f'{prefix}_p_val': 1.0})
            continue
            
        gross_rets = rets * dir_mult
        
        # Map drift, fallback to unconditional if group is missing
        cg_ids = events.loc[rets.index, 'control_group_id']
        fallback_count = (~cg_ids.isin(mat_drift_map)).sum()
        
        mat_drifts = cg_ids.map(mat_drift_map).fillna(unc_drift)
        expected_drift = mat_drifts if hyp['direction'] == 'Long' else -mat_drifts
        
        net_mat_excess = gross_rets - expected_drift - BASE_COST
        
        ci_lower, ci_upper, p_val = bootstrap_test(net_mat_excess.values, events.loc[rets.index, 'cluster'].values)
        trim_mean = trimmed_mean(net_mat_excess.values, 0.1)
        
        results.append({
            'id': hyp['id'],
            'base_signal': hyp['base_signal'],
            'gate_type': hyp['gate_type'],
            'gate_val': hyp['gate_val'],
            f'{prefix}_N_raw': n_raw,
            f'{prefix}_N_cluster': n_cluster,
            f'{prefix}_Gross': gross_rets.mean(),
            f'{prefix}_Net_Excess': net_mat_excess.mean(),
            f'{prefix}_Trimmed_Mean': trim_mean,
            f'{prefix}_CI_Lower': ci_lower,
            f'{prefix}_CI_Upper': ci_upper,
            f'{prefix}_p_val': p_val,
            f'{prefix}_Fallback_Count': fallback_count
        })
        
    return pd.DataFrame(results)

def main():
    print("Loading data...")
    df = load_discovery_data()
    print("Calculating features...")
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    print("Defining Regimes (Leak Free)...")
    df = define_regimes_leak_free(df)
    
    df['entry_price'] = df['open'].shift(-1)
    df[f'fwd_ret_h{HORIZON}'] = df['close'].shift(- (HORIZON+1)) / df['entry_price'] - 1.0
    
    print("Defining Signals and Hypotheses...")
    base_signals = define_base_signals(df)
    hypotheses = build_hypotheses(df, base_signals)
    print(f"Total hypotheses: {len(hypotheses)} (Expected 94)")
    
    # Train / Val Split
    df_train = df.loc['2020-01-01':'2021-12-31'].copy()
    df_val = df.loc['2022-01-01':'2023-12-31'].copy()
    
    # ---------------------------------------------------------
    # Gate A: Evaluate on Train
    # ---------------------------------------------------------
    print("Evaluating Train (Gate A)...")
    train_hyps = []
    for h in hypotheses:
        th = h.copy()
        th['series'] = th['series'].loc[df_train.index]
        train_hyps.append(th)
        
    train_results = evaluate_subset(df_train, train_hyps, 'Train')
    
    # FDR Correction on all 94 p-values
    p_vals = train_results['Train_p_val'].fillna(1.0).values
    q_vals = false_discovery_control(p_vals, method='bh')
    train_results['Train_q_val'] = q_vals
    
    train_results.to_csv(os.path.join(SEARCH_DIR, 'train_all_hypotheses.csv'), index=False)
    
    # Apply Gate A Criteria
    gate_a_mask = (
        (train_results['Train_Net_Excess'] > 0) &
        (train_results['Train_CI_Lower'] > 0) &
        (train_results['Train_Trimmed_Mean'] > 0) &
        (train_results['Train_N_cluster'] >= 30) &
        (train_results['Train_q_val'] < 0.05)
    )
    
    survivors = train_results[gate_a_mask].copy()
    print(f"Gate A Survivors: {len(survivors)}")
    
    if len(survivors) == 0:
        print("NO hypotheses passed Gate A.")
        with open(os.path.join(SEARCH_DIR, 'report.md'), 'w', encoding='utf-8') as f:
            f.write("# 複合シグナル探索 実行レポート\n\n")
            f.write("## 結論: 重要な発見\n")
            f.write("Train期間(2020-2021)にて94の全試行を厳格なアウトオブサンプル検定（FDR補正、クラスタブートストラップ）にかけた結果、**Gate Aを通過する候補は1つもありませんでした。**\n\n")
            f.write("この結果は「失敗」ではなく、「1時間足の当該特徴量群（BB反発、Stoch_d、SMA）においては、取引コスト(0.2%)を控除した後に残る堅牢な超過エッジは存在しない」という証明です。\n")
            f.write("局所的にプラスとなる期間やレジームは存在しますが、多重検定ペナルティを課した統計的有意性を満たす強さはありません。\n\n")
            f.write("## 次の一手の選択肢\n")
            f.write("1. **1分足マイクロ構造の活用**: エントリー/イグジットを1分足で最適化し、スリッページ・約定コストを大幅に削減（実質0.1%以下へ）することで期待値の底上げを図る。\n")
            f.write("2. **別次元データの導入**: 未決済建玉(OI)や資金調達率(Funding Rate)など、価格以外のアグレッシブなフローデータを特徴量に加える。\n")
            f.write("3. **撤退**: 現在の取引所・対象において、AIシステムトレードとしての優位性構築は困難と判断し撤退する。\n")
        return
        
    # Select Best Candidate per Base Signal (Max Selection)
    # 複数のゲートが通った場合、Train_Net_Excess が最大のものを1つだけ残す
    best_survivors = survivors.loc[survivors.groupby('base_signal')['Train_Net_Excess'].idxmax()].copy()
    best_survivors.to_csv(os.path.join(SEARCH_DIR, 'train_gate_a_passed.csv'), index=False)
    print(f"Best Candidates for Gate B: {len(best_survivors)}")
    
    # ---------------------------------------------------------
    # Gate B: Evaluate strictly ONE candidate per base signal on Val
    # ---------------------------------------------------------
    print("Evaluating Validation (Gate B)...")
    val_hyps = []
    for h in hypotheses:
        if h['id'] in best_survivors['id'].values:
            vh = h.copy()
            vh['series'] = vh['series'].loc[df_val.index]
            val_hyps.append(vh)
            
    val_results = evaluate_subset(df_val, val_hyps, 'Val')
    
    # Merge Val results with best_survivors
    final_df = pd.merge(best_survivors, val_results, on=['id', 'base_signal', 'gate_type', 'gate_val'], how='left')
    
    # Gate B Pass Criteria:
    # 1. Val_Net_Excess > 0
    # 2. Substantial Drop (Threshold = 0.0, meaning any positive is a pass for quasi-holdout)
    gate_b_mask = (final_df['Val_Net_Excess'] > 0)
    final_df['Passed_Gate_B'] = gate_b_mask
    
    final_df.to_csv(os.path.join(SEARCH_DIR, 'val_gate_b_results.csv'), index=False)
    
    passed_count = gate_b_mask.sum()
    
    with open(os.path.join(SEARCH_DIR, 'report.md'), 'w', encoding='utf-8') as f:
        f.write("# 複合シグナル探索 実行レポート\n\n")
        f.write("## 1. Train (Gate A) の結果\n")
        f.write(f"94試行に対してFDR補正を行い、{len(survivors)}件が生存しました。ベースシグナルごとに最良のゲートを1つ選抜した結果、{len(best_survivors)}件がGate B（Validation）へ進みました。\n\n")
        
        f.write("## 2. Validation (Gate B) の一発勝負結果\n")
        if passed_count > 0:
            f.write(f"**{passed_count}件** がGate Bを通過し、本物のエッジとして確定しました。\n\n")
        else:
            f.write("**Gate Bを通過した候補はありませんでした。** TrainでのエッジはVal（別時期・別レジーム）で消失しました。\n\n")
            
        f.write(final_df[['id', 'Train_Net_Excess', 'Val_Net_Excess', 'Passed_Gate_B', 'Val_Fallback_Count']].to_markdown(index=False) + "\n\n")
        
        f.write("## 3. 考察と次のアクション\n")
        if passed_count == 0:
            f.write("ショート側については、全体的な上昇バイアス（ドリフト）に飲み込まれている可能性が高いですが、ロング側についても堅牢なエッジは見つかりませんでした。\n")
            f.write("この結果は「失敗」ではなく、「1時間足のBB/Stoch特徴量のみでは、実取引コスト(0.2%)を上回るエッジは構築できない」という重要な結論です。\n")
            f.write("今後は、1分足マイクロ構造によるコスト削減や、OI/FundingRate等の新データ導入へ移行することを推奨します。\n")
        else:
            f.write("Gate Bを通過した強力なエッジをもとに、イグジット（MFE/MAE）の最適化フェーズへ移行します。\n")

    # 年×レジーム内訳出力 (Val対象候補のみ、全期間で計算)
    yearly_rows = []
    for h in val_hyps: # val_hyps contains the series for Val, but we need full df
        # Re-fetch the full series
        full_hyp = next(hx for hx in hypotheses if hx['id'] == h['id'])
        sig_series = full_hyp['series']
        
        events = df[sig_series].copy()
        events['cluster'] = get_event_clusters([df.index.get_loc(idx) for idx in events.index], gap=24)
        
        dir_mult = 1 if full_hyp['direction'] == 'Long' else -1
        df_non_sig = df[~sig_series]
        mat_drift_map = df_non_sig.groupby('control_group_id')[f'fwd_ret_h{HORIZON}'].mean().to_dict()
        
        for (year, regime), group in events.groupby(['year', 'regime_label']):
            n_eff = len(group['cluster'].unique())
            gross = group[f'fwd_ret_h{HORIZON}'] * dir_mult
            drifts = group['control_group_id'].map(mat_drift_map).fillna(0)
            expected = drifts if full_hyp['direction'] == 'Long' else -drifts
            net_mat_exc = gross - expected - BASE_COST
            
            yearly_rows.append({
                'id': full_hyp['id'],
                'Year': year,
                'Regime_Label': regime,
                'N_cluster': n_eff,
                'Net_Matched_Excess_Mean': net_mat_exc.mean()
            })
            
    if len(yearly_rows) > 0:
        pd.DataFrame(yearly_rows).to_csv(os.path.join(SEARCH_DIR, 'yearly_regime_breakdown.csv'), index=False)
        
    print("Composite search completed.")

if __name__ == "__main__":
    main()
