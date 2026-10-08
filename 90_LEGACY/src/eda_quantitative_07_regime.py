import os
import gc
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from src.data_loader import load_discovery_data
from src.features import calculate_fib_features
from src.config import BASE_COST

OUT_DIR = r"D:\work\AI-Trade\SakanaAISystemTrade\reports\EDA\07_regime"
os.makedirs(OUT_DIR, exist_ok=True)

def main():
    print("Loading 1h Context Data (2020-2023)...")
    df_1h = load_discovery_data()
    df_1h = calculate_fib_features(df_1h, 19)
    
    # Target and Costs (24h)
    df_1h['entry_price'] = df_1h['open'].shift(-1)
    df_1h['exit_price_24h'] = df_1h['close'].shift(-24)
    df_1h['fwd_ret_24h_gross'] = (df_1h['exit_price_24h'] / df_1h['entry_price']) - 1.0
    df_1h['fwd_ret_24h'] = df_1h['fwd_ret_24h_gross'] - BASE_COST
    df_1h['win_24h'] = (df_1h['fwd_ret_24h'] > 0).astype(int)
    
    # MAE (24h)
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=24)
    df_1h['min_low_24h'] = df_1h['low'].rolling(window=indexer).min()
    tr = np.maximum(df_1h['high'] - df_1h['low'], 
                    np.maximum(abs(df_1h['high'] - df_1h['close'].shift(1)), 
                               abs(df_1h['low'] - df_1h['close'].shift(1))))
    df_1h['ATR_14'] = tr.rolling(14).mean()
    df_1h['MAE_ATR'] = (df_1h['min_low_24h'] - df_1h['entry_price']) / df_1h['ATR_14']
    
    # Feature calcs
    sma_slope_cols = [c for c in df_1h.columns if 'SMA_slope' in c]
    df_1h['pos_slopes_count'] = (df_1h[sma_slope_cols] > 0).sum(axis=1)
    df_1h['dist_sma144'] = (df_1h['close'] - df_1h['FIB_11_SMA']) / df_1h['ATR_14']
    
    # --- REGIME DEFINITION (Leak-Free) ---
    long_sma = df_1h['FIB_11_SMA']
    long_slope = df_1h['FIB_11_SMA_slope']
    df_1h['atr_pct'] = df_1h['ATR_14'] / df_1h['close']
    df_1h['atr_pct_median'] = df_1h['atr_pct'].expanding(min_periods=24).median()
    
    is_bull = (df_1h['close'] > long_sma) & (long_slope > 0)
    is_bear = (df_1h['close'] < long_sma) & (long_slope < 0)
    df_1h['Trend_Regime'] = 'Range'
    df_1h.loc[is_bull, 'Trend_Regime'] = 'Bull'
    df_1h.loc[is_bear, 'Trend_Regime'] = 'Bear'
    
    df_1h['Vol_Regime'] = np.where(df_1h['atr_pct'] > df_1h['atr_pct_median'], 'HighVol', 'LowVol')
    df_1h['Regime'] = df_1h['Trend_Regime'] + '_' + df_1h['Vol_Regime']
    
    df_years = {str(y): df_1h.loc[f'{y}-01-01':f'{y}-12-31'].copy() for y in range(2020, 2024)}
    
    report_lines = []
    report_lines.append("# EDA 07: レジーム別一貫性 (MoE/状態分岐仮説) の検証\n")
    report_lines.append("> 全期間では非定常（年次で符号が反転）となる構造が、**同一レジーム内であれば年を跨いでも一貫して機能するのか**を検証します。\n\n")

    structures = {
        'Trend(Slopes>=12)': lambda d: d['pos_slopes_count'] >= 12,
        'Reversion(Dist<=-2)': lambda d: d['dist_sma144'] <= -2,
        'DipBuy(Short<Long & Slope>0 & Stoch<80)': lambda d: (d['FIB_8_SMA'] < d['FIB_11_SMA']) & (d['FIB_11_SMA_slope'] > 0) & (d['FIB_8_stoch_d'] <= 80),
        'PerfectOrder': lambda d: (d['FIB_8_SMA'] > d['FIB_9_SMA']) & (d['FIB_9_SMA'] > d['FIB_10_SMA']) & (d['FIB_10_SMA'] > d['FIB_11_SMA']),
        'ReverseOrder': lambda d: (d['FIB_8_SMA'] < d['FIB_9_SMA']) & (d['FIB_9_SMA'] < d['FIB_10_SMA']) & (d['FIB_10_SMA'] < d['FIB_11_SMA'])
    }
    
    regimes = df_1h['Regime'].dropna().unique()
    
    consistent_structures = []

    for s_name, s_func in structures.items():
        report_lines.append(f"## {s_name}\n")
        report_lines.append("| レジーム | 年 | ベースN | ベースRet | 条件N | 条件Ret | 差分(Delta) | 勝率 | Mean MAE |\n")
        report_lines.append("|---|---|---|---|---|---|---|---|---|\n")
        
        for reg in sorted(regimes):
            deltas = []
            for year, d in df_years.items():
                d_reg = d[d['Regime'] == reg].dropna(subset=['fwd_ret_24h'])
                base_n = len(d_reg)
                if base_n < 50:
                    continue
                base_ret = d_reg['fwd_ret_24h'].mean()
                
                mask = s_func(d_reg)
                sub = d_reg[mask]
                cond_n = len(sub)
                
                if cond_n >= 50:
                    cond_ret = sub['fwd_ret_24h'].mean()
                    cond_win = sub['win_24h'].mean()
                    cond_mae = sub['MAE_ATR'].mean()
                    delta = cond_ret - base_ret
                    deltas.append(delta)
                    report_lines.append(f"| {reg} | {year} | {base_n} | {base_ret:.2%} | {cond_n} | {cond_ret:.2%} | **{delta:+.2%}** | {cond_win:.1%} | {cond_mae:.2f} |\n")
                else:
                    report_lines.append(f"| {reg} | {year} | {base_n} | {base_ret:.2%} | {cond_n} | - | - | - | - |\n")
            
            if len(deltas) == 4 and all(x > 0 for x in deltas):
                msg = f"> ✅ **{reg} レジームにおいて、4年間一貫してベースラインを上回る（+Delta）構造が見られました。**\n\n"
                report_lines.append(msg)
                consistent_structures.append(f"{s_name} in {reg} (Positive)")
            elif len(deltas) == 4 and all(x < 0 for x in deltas):
                msg = f"> ✅ **{reg} レジームにおいて、4年間一貫してベースラインを下回る（逆エッジ）構造が見られました。**\n\n"
                report_lines.append(msg)
                consistent_structures.append(f"{s_name} in {reg} (Negative)")
            else:
                pass 
        report_lines.append("\n")
                
    report_lines.append("## 結論と提言\n")
    if consistent_structures:
        report_lines.append("以下の構造が、特定レジーム内で4年間一貫して機能することが確認されました。\n")
        for st in consistent_structures:
            report_lines.append(f"- {st}\n")
        report_lines.append("\n**提言**: 特定のレジーム内で一貫性を持つ構造が発見されました。これらはMoE（Mixture of Experts）モデル等の入力特徴量として極めて有望であり、次フェーズでの検定対象とすべきです。\n")
    else:
        report_lines.append("価格系テクニカル指標には、レジーム内で分割したとしても**「4年間にわたり一貫してベースラインをアウトパフォーム/アンダーパフォームし続ける頑健な構造」が全く存在しない（あるいはN不足で確認できない）**ことが証明されました。\n\n")
        report_lines.append("**提言**: 価格やオシレーターから抽出される単独のテクニカルパターンは、市場の学習と効率化によって数年で効力を失います。これ以上の価格系テクニカルの探索（パラメータ最適化や組合せ）は過学習に直結するため撤退を推奨します。実運用で勝つという北極星に照らせば、価格以外のデータ（OI、Funding Rate等の市場内部構造）の導入、またはより高度な機械学習モデルへの移行が必須です。\n")
        
    with open(os.path.join(OUT_DIR, "report.md"), 'w', encoding='utf-8') as f:
        f.writelines(report_lines)
        
    print("EDA 07 completed. Report generated.")

if __name__ == "__main__":
    main()
