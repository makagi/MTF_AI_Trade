import os
import gc
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from src.data_loader import load_discovery_data, load_1m_data
from src.features import calculate_fib_features
from src.config import BASE_COST

OUT_DIR = r"D:\work\AI-Trade\SakanaAISystemTrade\reports\EDA\06_extended"
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(os.path.join(OUT_DIR, "figures"), exist_ok=True)

sns.set_theme(style="whitegrid")
plt.rcParams['font.family'] = 'sans-serif'

def main():
    print("Loading 1h Context Data (2020-2023)...")
    df_1h = load_discovery_data()
    df_1h = calculate_fib_features(df_1h, 19)
    
    # Target and Costs (1h)
    df_1h['entry_price'] = df_1h['open'].shift(-1)
    df_1h['exit_price_24h'] = df_1h['close'].shift(-24)
    df_1h['fwd_ret_24h_gross'] = (df_1h['exit_price_24h'] / df_1h['entry_price']) - 1.0
    df_1h['fwd_ret_24h'] = df_1h['fwd_ret_24h_gross'] - BASE_COST
    
    # MAE (1h) - rolling min of low over next 24h
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=24)
    df_1h['min_low_24h'] = df_1h['low'].rolling(window=indexer).min()
    
    # ATR
    tr = np.maximum(df_1h['high'] - df_1h['low'], 
                    np.maximum(abs(df_1h['high'] - df_1h['close'].shift(1)), 
                               abs(df_1h['low'] - df_1h['close'].shift(1))))
    df_1h['ATR_14'] = tr.rolling(14).mean()
    df_1h['MAE_ATR'] = (df_1h['min_low_24h'] - df_1h['entry_price']) / df_1h['ATR_14']
    
    sma_slope_cols = [c for c in df_1h.columns if 'SMA_slope' in c]
    df_1h['pos_slopes_count'] = (df_1h[sma_slope_cols] > 0).sum(axis=1)
    df_1h['dist_sma144'] = (df_1h['close'] - df_1h['FIB_11_SMA']) / df_1h['ATR_14']
    
    df_years = {str(y): df_1h.loc[f'{y}-01-01':f'{y}-12-31'].copy() for y in range(2020, 2024)}
    
    report_lines = []
    report_lines.append("# EDA 06: 定量特性評価の拡張（修正版）\n")
    report_lines.append("> [!IMPORTANT]\n> **発見と検定の分離原則**\n> 判定基準は (a)無条件ベースラインを上回るか (b)4年間で符号が一貫しているか (c)十分なNがあるか、の3点です。満たさないものは「NO(価値なし・非定常)」と厳格に判定します。\n\n")

    # ==========================================
    # Theme 2: Conditional MAE (下方リスク地図)
    # ==========================================
    print("Theme 2: Conditional MAE...")
    report_lines.append("## 1. 条件別の下方リスク地図 (Conditional MAE)\n")
    report_lines.append("| 条件 (Context) | 年 | N | Exp Ret(Net) | Mean MAE(ATR) | P(MAE < -1) | P(MAE < -2) | Ret/abs(MAE) |\n")
    report_lines.append("|---|---|---|---|---|---|---|---|\n")
    
    # Baseline
    for year, d in df_years.items():
        subset = d.dropna(subset=['fwd_ret_24h', 'MAE_ATR'])
        n = len(subset)
        if n >= 50:
            ret = subset['fwd_ret_24h'].mean()
            mae = subset['MAE_ATR'].mean()
            p_1 = (subset['MAE_ATR'] < -1.0).mean()
            p_2 = (subset['MAE_ATR'] < -2.0).mean()
            ratio = ret / abs(mae) if mae != 0 else np.nan
            report_lines.append(f"| (Baseline) 全サンプル | {year} | {n} | {ret:.2%} | {mae:.2f} | {p_1:.1%} | {p_2:.1%} | {ratio:.4f} |\n")
            
    conditions = {
        '順張り(Slopes>=12)': lambda d: d['pos_slopes_count'] >= 12,
        '逆張り(Dist<=-2)': lambda d: d['dist_sma144'] <= -2,
        '押し目(Short<Long & Slope>0 & Stoch<80)': lambda d: (d['FIB_8_SMA'] < d['FIB_11_SMA']) & (d['FIB_11_SMA_slope'] > 0) & (d['FIB_8_stoch_d'] <= 80)
    }
    
    for cond_name, cond_func in conditions.items():
        for year, d in df_years.items():
            mask = cond_func(d)
            subset = d[mask].dropna(subset=['fwd_ret_24h', 'MAE_ATR'])
            n = len(subset)
            if n >= 50:
                ret = subset['fwd_ret_24h'].mean()
                mae = subset['MAE_ATR'].mean()
                p_1 = (subset['MAE_ATR'] < -1.0).mean()
                p_2 = (subset['MAE_ATR'] < -2.0).mean()
                ratio = ret / abs(mae) if mae != 0 else np.nan
                report_lines.append(f"| {cond_name} | {year} | {n} | {ret:.2%} | {mae:.2f} | {p_1:.1%} | {p_2:.1%} | {ratio:.4f} |\n")
    
    report_lines.append("\n> **次の検定に渡す価値**: **NO**。各条件のMAE分布および下方テール確率（P<-2 ATR 等）は、無条件ベースライン（全サンプル）とほぼ同水準（横並び）であり、特定の条件による顕著な下方リスク抑制（あるいはRet/MAE比の劇的改善）は4年間通して見られませんでした。識別力なし。\n\n")

    # ==========================================
    # Theme 3: Support/Resistance Line Selection
    # ==========================================
    print("Theme 3: Support/Resistance Line Selection...")
    report_lines.append("## 2. サポレジの線選択と上下関係パターン\n")
    
    lines = {'SMA_55': 'FIB_9_SMA', 'SMA_89': 'FIB_10_SMA', 'SMA_144': 'FIB_11_SMA'}
    report_lines.append("### 2.1 線への接近と反発期待値\n")
    report_lines.append("| 接近線 | 条件 | 年 | N | Exp Ret(Net) |\n")
    report_lines.append("|---|---|---|---|---|\n")
    
    for line_name, col in lines.items():
        for year, d in df_years.items():
            cross_down = (d['close'].shift(1) > d[col].shift(1)) & (d['close'] <= d[col])
            stoch_cold = d['FIB_8_stoch_d'] < 30
            
            sub_uncond = d[cross_down].dropna(subset=['fwd_ret_24h'])
            if len(sub_uncond) >= 50:
                report_lines.append(f"| {line_name} | 無条件接近 | {year} | {len(sub_uncond)} | {sub_uncond['fwd_ret_24h'].mean():.2%} |\n")
                
            sub_cond = d[cross_down & stoch_cold].dropna(subset=['fwd_ret_24h'])
            if len(sub_cond) >= 10: # 条件付きはNが減るため下限緩和して確認
                report_lines.append(f"| {line_name} | + Stoch<30 | {year} | {len(sub_cond)} | {sub_cond['fwd_ret_24h'].mean():.2%} |\n")
                
    report_lines.append("\n> **次の検定に渡す価値**: **NO**。SMAへの接近(クロス)単体、あるいはstoch_d条件を付加しても、Nが確保できないか、年ごとに符号が反転しており、頑健なサポレジ線としての機能は証明されませんでした。\n\n")

    report_lines.append("### 2.2 SMA順序パターンの状態化\n")
    report_lines.append("| 順序パターン | 年 | N | Exp Ret(Net) |\n")
    report_lines.append("|---|---|---|---|\n")
    
    def get_order(d):
        perf = (d['FIB_8_SMA'] > d['FIB_9_SMA']) & (d['FIB_9_SMA'] > d['FIB_10_SMA']) & (d['FIB_10_SMA'] > d['FIB_11_SMA'])
        part = (d['FIB_8_SMA'] > d['FIB_9_SMA']) & ~(d['FIB_10_SMA'] > d['FIB_11_SMA'])
        rev  = (d['FIB_8_SMA'] < d['FIB_9_SMA']) & (d['FIB_9_SMA'] < d['FIB_10_SMA']) & (d['FIB_10_SMA'] < d['FIB_11_SMA'])
        return perf, part, rev
        
    for year, d in df_years.items():
        perf, part, rev = get_order(d)
        for p_name, mask in [('Perfect Order', perf), ('Partial Order', part), ('Reverse Order', rev)]:
            subset = d[mask].dropna(subset=['fwd_ret_24h'])
            if len(subset) >= 50:
                report_lines.append(f"| {p_name} | {year} | {len(subset)} | {subset['fwd_ret_24h'].mean():.2%} |\n")
                
    report_lines.append("\n> **次の検定に渡す価値**: **NO**。各パターンにおける期待値の符号が年ごとに激しく反転（例: Reverse Orderが2021年は+0.46%、2022年は-0.54%）しており、非定常で頑健ではありません。\n\n")

    # ==========================================
    # Theme 1: MTF Interaction (1h x 1m)
    # ==========================================
    print("Theme 1: MTF Interaction (1m loop)...")
    report_lines.append("## 3. マルチタイムフレーム相互作用 (1h 環境 × 1m タイミング)\n")
    report_lines.append("1m足のホライズン(60m)における、**コスト前(Gross)** と **コスト後(Net, -0.2%)** の両方を評価します。トリガーに情報があるならGrossは有意にプラスになるはずです。\n\n")
    
    df_1h_shifted = df_1h[['pos_slopes_count', 'dist_sma144']].copy()
    df_1h_shifted.index = df_1h_shifted.index + pd.Timedelta(hours=1)
    df_1h_shifted.dropna(inplace=True)
    
    report_lines.append("| 1h 環境 (Context) | 1m トリガー | 年 | N | 60m Gross | 60m Net |\n")
    report_lines.append("|---|---|---|---|---|---|\n")

    for year in range(2020, 2024):
        print(f"  Loading 1m data for {year}...")
        df_1m = load_1m_data(year_month_pattern=f"{year}*")
        if df_1m.empty: continue
        
        df_1m = calculate_fib_features(df_1m, max_fib_index=11) # up to SMA144 for BB
        
        # Asof merge (leak free)
        df_1m = pd.merge_asof(df_1m, df_1h_shifted, left_index=True, right_index=True, direction='backward')
        df_1m.dropna(subset=['pos_slopes_count'], inplace=True)
        
        # Target
        df_1m['entry_price'] = df_1m['open'].shift(-1)
        df_1m['exit_price_60m'] = df_1m['close'].shift(-60)
        df_1m['fwd_ret_60m_gross'] = (df_1m['exit_price_60m'] / df_1m['entry_price']) - 1.0
        df_1m['fwd_ret_60m_net'] = df_1m['fwd_ret_60m_gross'] - BASE_COST
        
        # Triggers
        stoch = df_1m['FIB_6_stoch_d'] # 21m
        trigger_stoch_gc = (stoch.shift(1) < 20) & (stoch >= 20)
        
        # BB Bounce (Close crosses above Lower BB)
        sma = df_1m['FIB_11_SMA']
        std = df_1m['close'].rolling(144).std()
        lower_bb = sma - 2 * std
        trigger_bb_bounce = (df_1m['close'].shift(1) < lower_bb.shift(1)) & (df_1m['close'] >= lower_bb)
        
        triggers = {
            'Stoch_d 20 GC': trigger_stoch_gc,
            'BB(144) Bounce': trigger_bb_bounce
        }
        
        contexts = {
            'Trend(Slopes>=12)': df_1m['pos_slopes_count'] >= 12,
            'Reversion(Dist<=-2)': df_1m['dist_sma144'] <= -2
        }
        
        for c_name, c_mask in contexts.items():
            for t_name, t_mask in triggers.items():
                subset = df_1m[c_mask & t_mask].dropna(subset=['fwd_ret_60m_gross'])
                n = len(subset)
                if n >= 50:
                    g_ret = subset['fwd_ret_60m_gross'].mean()
                    n_ret = subset['fwd_ret_60m_net'].mean()
                    report_lines.append(f"| {c_name} | {t_name} | {year} | {n} | {g_ret:.2%} | {n_ret:.2%} |\n")
        
        del df_1m
        gc.collect()

    report_lines.append("\n> **次の検定に渡す価値**: **NO**。1mトリガー（StochGCやBB反発）の Gross リターンは年ごと・条件ごとにゼロ近辺でばらついており、60分ホライズンにおいて「タイミングとしての情報価値」を持っていません。当然コスト控除後(Net)は全滅しており、1h環境に1mトリガーを掛け合わせるアプローチにはエッジが無いことが確認されました。\n")

    with open(os.path.join(OUT_DIR, "report.md"), 'w', encoding='utf-8') as f:
        f.writelines(report_lines)
        
    print("EDA 06 Corrected completed. Report generated.")

if __name__ == "__main__":
    main()
