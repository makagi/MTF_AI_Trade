import os
import pandas as pd
import numpy as np
from src.data_loader import load_1m_data

AUDIT_DIR = r"D:\work\AI-Trade\SakanaAISystemTrade\reports\Audits\04_data_time_audit"
os.makedirs(AUDIT_DIR, exist_ok=True)

def main():
    print("Loading raw 1h data...")
    file_path = r"D:\work\AI-Trade\Data\BTCUSD_1h\BTCUSD_OHLC_all.csv"
    df_raw = pd.read_csv(file_path)
    df_raw['DateTime'] = pd.to_datetime(df_raw['DateTime'])
    
    # 2023-12-31以前のみを対象とする
    df_raw = df_raw[df_raw['DateTime'] <= '2023-12-31'].copy()
    
    # 1. タイムゾーン情報
    tz_info = str(df_raw['DateTime'].dt.tz)
    
    # 2. 重複チェック
    dups = df_raw[df_raw.duplicated(subset=['DateTime'], keep=False)].copy()
    if not dups.empty:
        dups.to_csv(os.path.join(AUDIT_DIR, 'duplicate_timestamps.csv'), index=False)
    else:
        pd.DataFrame(columns=df_raw.columns).to_csv(os.path.join(AUDIT_DIR, 'duplicate_timestamps.csv'), index=False)
        
    # 以降は一意なインデックスで処理
    df = df_raw.drop_duplicates(subset=['DateTime'], keep='last').copy()
    df.set_index('DateTime', inplace=True)
    df.sort_index(inplace=True)
    
    # 非単調性のチェック (sort前に行うべきだが、既にsortしてしまったので元の配列でチェック)
    is_monotonic = df_raw['DateTime'].is_monotonic_increasing
    
    # 3. 時刻差の件数分布
    diffs = df.index.to_series().diff()
    diffs_hr = diffs.dt.total_seconds() / 3600
    
    interval_counts = diffs_hr.value_counts().reset_index()
    interval_counts.columns = ['Interval_Hours', 'Count']
    interval_counts.to_csv(os.path.join(AUDIT_DIR, 'time_interval_counts.csv'), index=False)
    
    # 2時間以上の欠損区間
    gap_df = pd.DataFrame({
        'Gap_Start': df.index[np.where(diffs_hr > 1.0)[0] - 1],
        'Gap_End': df.index[diffs_hr > 1.0],
        'Gap_Hours': diffs_hr[diffs_hr > 1.0].values
    })
    gap_df.to_csv(os.path.join(AUDIT_DIR, 'missing_intervals.csv'), index=False)
    
    # 4. OHLCの整合性チェック
    integrity_issues = []
    
    nan_rows = df[df[['open', 'high', 'low', 'close']].isna().any(axis=1)].copy()
    bad_high = df[df['high'] < df[['open', 'close']].max(axis=1) - 1e-4].copy()
    bad_low = df[df['low'] > df[['open', 'close']].min(axis=1) + 1e-4].copy()
    bad_high_low = df[df['high'] < df['low']].copy()
    bad_zero = df[(df['open'] <= 0) | (df['high'] <= 0) | (df['low'] <= 0) | (df['close'] <= 0)].copy()
    
    for issue_type, idf in [('NaN Found', nan_rows), ('High < Max(O,C)', bad_high), 
                            ('Low > Min(O,C)', bad_low), ('High < Low', bad_high_low), 
                            ('Price <= 0', bad_zero)]:
        if not idf.empty:
            for idx, row in idf.iterrows():
                row_dict = row.to_dict()
                row_dict['Issue'] = issue_type
                row_dict['DateTime'] = idx
                integrity_issues.append(row_dict)
                
    if integrity_issues:
        pd.DataFrame(integrity_issues).to_csv(os.path.join(AUDIT_DIR, 'ohlc_integrity_issues.csv'), index=False)
    else:
        pd.DataFrame(columns=['DateTime', 'Issue', 'open', 'high', 'low', 'close']).to_csv(os.path.join(AUDIT_DIR, 'ohlc_integrity_issues.csv'), index=False)

    # 5. 1分足との突き合わせによる時刻の定義(バー開始時刻か終了時刻か)
    print("Loading 1m data for timeframe alignment check...")
    df_1m = load_1m_data('202106') # 2021年6月を使用
    
    align_results = []
    if not df_1m.empty:
        target_date = '2021-06-01'
        df_1m_day = df_1m.loc[target_date].copy()
        
        for hr in range(1, 23):
            t_str = f"{target_date} {hr:02d}:00:00"
            if t_str not in df.index: continue
            ohlc_1h = df.loc[t_str]
            
            # Start time hypothesis: 10:00 represents 10:00:00 to 10:59:59
            start_hyp = df_1m_day.between_time(f"{hr:02d}:00", f"{hr:02d}:59")
            match_start = False
            if not start_hyp.empty:
                match_start = (
                    abs(start_hyp['open'].iloc[0] - ohlc_1h['open']) < 1e-4 and
                    abs(start_hyp['high'].max() - ohlc_1h['high']) < 1e-4 and
                    abs(start_hyp['low'].min() - ohlc_1h['low']) < 1e-4 and
                    abs(start_hyp['close'].iloc[-1] - ohlc_1h['close']) < 1e-4
                )
                
            # End time hypothesis: 10:00 represents 09:00:00 to 09:59:59
            # (Note: sometimes 1m bars themselves are end-time, so 09:01 to 10:00. We will check 09:00 to 09:59 first)
            end_hyp = df_1m_day.between_time(f"{hr-1:02d}:00", f"{hr-1:02d}:59")
            match_end = False
            if not end_hyp.empty:
                match_end = (
                    abs(end_hyp['open'].iloc[0] - ohlc_1h['open']) < 1e-4 and
                    abs(end_hyp['high'].max() - ohlc_1h['high']) < 1e-4 and
                    abs(end_hyp['low'].min() - ohlc_1h['low']) < 1e-4 and
                    abs(end_hyp['close'].iloc[-1] - ohlc_1h['close']) < 1e-4
                )
                
            align_results.append({
                '1h_Time': t_str,
                'Match_Start_Time_Hypothesis': match_start,
                'Match_End_Time_Hypothesis': match_end
            })
            
    pd.DataFrame(align_results).to_csv(os.path.join(AUDIT_DIR, 'timeframe_alignment.csv'), index=False)
    
    # サンプル出力
    df.head(20).to_csv(os.path.join(AUDIT_DIR, 'sample_rows.csv'))
    
    # 6. Report Generation
    with open(os.path.join(AUDIT_DIR, 'report.md'), 'w', encoding='utf-8') as f:
        f.write("# 時系列データ品質監査 (Data & Time Audit)\n\n")
        f.write(f"- インデックスのタイムゾーン: `{tz_info}`\n")
        f.write(f"- インデックスの単調増加性: `{is_monotonic}`\n")
        f.write(f"- 重複時刻の件数: `{len(dups)}`件\n")
        f.write(f"- 2時間以上の欠損区間の件数: `{len(gap_df)}`件\n")
        f.write(f"- OHLC不整合の件数: `{len(integrity_issues)}`件\n\n")
        
        f.write("## バー時刻の意味 (1h vs 1m 照合)\n")
        if align_results:
            match_start_count = sum(r['Match_Start_Time_Hypothesis'] for r in align_results)
            match_end_count = sum(r['Match_End_Time_Hypothesis'] for r in align_results)
            if match_start_count > match_end_count:
                f.write("判定: **バー時刻は開始時刻（Start Time）** です。T時刻のバーはT〜T+59分の集計です。\n")
            elif match_end_count > match_start_count:
                f.write("判定: **バー時刻は終了時刻（End Time）または直前1時間の集計** です。\n")
            else:
                f.write("判定: **不明 (Unknown)**。1分足との完全一致が確認できませんでした。\n")
        else:
            f.write("判定: 1分足データが読み込めず未実施。\n")
            
        f.write("\n## 24hホライズンの是正と欠損の影響\n")
        f.write("これまでの `close.shift(-(24+1))` は25行先を参照しており、オフバイワン・エラーが存在しました。\n")
        f.write("正しい `close.shift(-24)` への修正が必要です。\n")
        f.write("ただし、欠損区間（Missing Intervals）が存在する場合、単純な行シフトでは「実時間での24時間後」とズレが生じます。\n")
        f.write("今後の検証では、シフトではなくインデックスのタイムスタンプ（T + 24h）を用いた厳密な出口価格の取得、および実時間ベースのクラスタリング（`current_ts - prev_ts <= 24h`）を適用します。\n")
        
    print("Audit Data Time completed.")

if __name__ == "__main__":
    main()
