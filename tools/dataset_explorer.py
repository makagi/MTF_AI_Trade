import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os

# Page Config
st.set_page_config(page_title="Exhaustive Dataset Explorer", layout="wide", page_icon="📈")

st.title("📈 Exhaustive MTF Dataset Explorer")
st.markdown("網羅的データセット（Parquet）から、任意の期間と特徴量（19層のフィボナッチSMA、ボリンジャーバンド、AFS等）を動的に選択して可視化します。")

# Data Loading
@st.cache_data
def load_data():
    path = r"D:\work\AI-Trade\Data\processed\BTCUSD_1h_features_exhaustive.parquet"
    if not os.path.exists(path):
        st.error(f"Dataset not found at {path}. Run build_features.py first.")
        return None
    
    # Load data
    df = pd.read_parquet(path)
    return df

df = load_data()

if df is not None:
    # Sidebar UI
    st.sidebar.header("📊 Chart Controls")
    
    # Date Range Selection
    min_date = df.index.min().date()
    max_date = df.index.max().date()
    
    date_range = st.sidebar.date_input(
        "Select Date Range",
        value=(pd.to_datetime('2023-01-01').date(), pd.to_datetime('2023-03-01').date()),
        min_value=min_date,
        max_value=max_date
    )
    
    if len(date_range) == 2:
        start_date, end_date = date_range
        mask = (df.index.date >= start_date) & (df.index.date <= end_date)
        df_plot = df.loc[mask]
        
        # Feature Selection
        all_columns = df.columns.tolist()
        base_cols = ['open', 'high', 'low', 'close', 'volume']
        feature_cols = [c for c in all_columns if c not in base_cols]
        
        # Filter for easier selection
        sma_cols = [c for c in feature_cols if 'SMA' in c and 'slope' not in c and 'dist' not in c]
        bb_cols = [c for c in feature_cols if 'BB' in c]
        afs_cols = [c for c in feature_cols if 'stoch_d' in c and 'slope' not in c]
        
        selected_smas = st.sidebar.multiselect("Select SMAs", sma_cols, default=['FIB_11_SMA', 'FIB_12_SMA', 'FIB_13_SMA'])
        selected_afs = st.sidebar.multiselect("Select AFS (Momentum)", afs_cols, default=[])
        selected_bb = st.sidebar.multiselect("Select Bollinger Bands", bb_cols, default=[])
        
        # Plotting
        st.subheader(f"Price Action & Selected Features ({start_date} to {end_date})")
        
        # Create figure with secondary y-axis if AFS is selected
        from plotly.subplots import make_subplots
        if selected_afs:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
        else:
            fig = make_subplots(rows=1, cols=1)
            
        # Add Candlesticks
        fig.add_trace(go.Candlestick(
            x=df_plot.index,
            open=df_plot['open'],
            high=df_plot['high'],
            low=df_plot['low'],
            close=df_plot['close'],
            name='Price'
        ), row=1, col=1)
        
        # Add SMAs
        for col in selected_smas:
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot[col], mode='lines', name=col, line=dict(width=1.5)), row=1, col=1)
            
        # Add BBs
        for col in selected_bb:
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot[col], mode='lines', name=col, line=dict(dash='dot', width=1)), row=1, col=1)
            
        # Add AFS to Subplot
        if selected_afs:
            for col in selected_afs:
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot[col], mode='lines', name=col.replace('_stoch_d', '_AFS')), row=2, col=1)
            
            # Add overbought/oversold lines
            fig.add_hline(y=80, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="green", row=2, col=1)
            fig.update_yaxes(title_text="AFS (0-100)", row=2, col=1)
            
        fig.update_layout(
            height=800 if selected_afs else 600,
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            margin=dict(l=20, r=20, t=30, b=20)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Show raw data
        with st.expander("Show Raw Data"):
            cols_to_show = base_cols + selected_smas + selected_bb + selected_afs
            st.dataframe(df_plot[cols_to_show].head(100))
    else:
        st.warning("Please select a valid date range.")
