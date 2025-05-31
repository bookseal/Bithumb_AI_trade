import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# 페이지 설정
st.set_page_config(
    page_title="Bitcoin AI Trading Dashboard",
    page_icon="📈",
    layout="wide"
)

# 데이터베이스 연결 및 데이터 로드
def load_trade_data():
    conn = sqlite3.connect('bitcoin_trading.db')
    query = "SELECT * FROM trades ORDER BY timestamp DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # 타임스탬프 처리
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 포트폴리오 가치 계산
    df['portfolio_value'] = df['krw_balance'] + (df['btc_balance'] * df['btc_price'])
    
    # 수익률 계산 (첫 거래 기준)
    if len(df) > 0:
        first_trade = df.iloc[-1]
        df['profit_loss'] = df['portfolio_value'] - first_trade['portfolio_value']
        df['profit_loss_pct'] = (df['profit_loss'] / first_trade['portfolio_value']) * 100
    
    return df

# 헤더
st.title("Bitcoin AI Trading Dashboard")

# 데이터 로드
df = load_trade_data()

# 최신 거래 정보
if not df.empty:
    latest = df.iloc[0]
    
    # 수익률 계산
    first_trade = df.iloc[-1]
    total_profit_pct = latest['profit_loss_pct']
    
    # 2개 컬럼으로 주요 정보 표시
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric(
            "포트폴리오 가치", 
            f"₩{latest['portfolio_value']:,.0f}",
            delta=f"{total_profit_pct:.2f}%"
        )
    
    with col2:
        st.metric(
            "최근 거래", 
            f"{latest['decision'].upper()} ({latest['percentage']}%)",
            delta=f"{latest['timestamp'].strftime('%Y-%m-%d %H:%M')}"
        )
    
    # BTC 및 현금 잔고
    st.markdown(f"""
    **BTC 잔고:** {latest['btc_balance']:.6f} BTC (₩{latest['btc_balance'] * latest['btc_price']:,.0f})  
    **KRW 잔고:** ₩{latest['krw_balance']:,.0f}
    """)

# 수익률 차트 (Plotly)
if not df.empty and len(df) > 1:
    st.subheader("수익률 변화")
    
    # 시간순으로 정렬
    df_sorted = df.sort_values('timestamp')
    
    # 기본 수익률 라인 차트 생성
    fig = go.Figure()
    
    # 0% 라인 추가
    fig.add_hline(y=0, line=dict(color='gray', width=1, dash='dash'))
    
    # 수익률 라인 추가
    fig.add_trace(go.Scatter(
        x=df_sorted['timestamp'], 
        y=df_sorted['profit_loss_pct'],
        mode='lines+markers',
        name='수익률',
        line=dict(color='blue', width=2),
        marker=dict(size=8)
    ))
    
    # 매수/매도 포인트 추가
    for decision, color in [('buy', 'green'), ('sell', 'red'), ('hold', 'orange')]:
        decision_df = df_sorted[df_sorted['decision'] == decision]
        if not decision_df.empty:
            fig.add_trace(go.Scatter(
                x=decision_df['timestamp'],
                y=decision_df['profit_loss_pct'],
                mode='markers',
                name=decision.upper(),
                marker=dict(color=color, size=12, symbol='circle')
            ))
    
    # 차트 레이아웃 설정
    fig.update_layout(
        title='첫 거래 대비 수익률 변화',
        xaxis_title='날짜',
        yaxis_title='수익률 (%)',
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        height=500,
        margin=dict(l=40, r=40, t=60, b=40)
    )
    
    # 호버 정보 커스터마이징
    fig.update_traces(
        hovertemplate='%{x}<br>수익률: %{y:.2f}%<br>'
    )
    
    # y축 포맷 설정
    fig.update_yaxes(ticksuffix='%')
    
    st.plotly_chart(fig, use_container_width=True)

# BTC 가격 차트 (Plotly)
if not df.empty:
    st.subheader("BTC 가격 변화")
    
    # 시간순으로 정렬
    df_sorted = df.sort_values('timestamp')
    
    # 기본 BTC 가격 차트 생성
    fig = go.Figure()
    
    # BTC 가격 라인 추가
    fig.add_trace(go.Scatter(
        x=df_sorted['timestamp'], 
        y=df_sorted['btc_price'],
        mode='lines+markers',
        name='BTC 가격',
        line=dict(color='orange', width=2),
        marker=dict(size=6)
    ))
    
    # 매수/매도 포인트 추가
    for decision, color, symbol in [('buy', 'green', 'triangle-up'), ('sell', 'red', 'triangle-down')]:
        decision_df = df_sorted[df_sorted['decision'] == decision]
        if not decision_df.empty:
            fig.add_trace(go.Scatter(
                x=decision_df['timestamp'],
                y=decision_df['btc_price'],
                mode='markers',
                name=decision.upper(),
                marker=dict(color=color, size=14, symbol=symbol)
            ))
    
    # 차트 레이아웃 설정
    fig.update_layout(
        title='BTC 가격 변화와 거래 결정',
        xaxis_title='날짜',
        yaxis_title='BTC 가격 (KRW)',
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        height=500,
        margin=dict(l=40, r=40, t=60, b=40)
    )
    
    # 호버 정보 커스터마이징
    fig.update_traces(
        hovertemplate='%{x}<br>가격: ₩%{y:,.0f}<br>'
    )
    
    # y축 포맷 설정
    fig.update_yaxes(tickformat=',.0f')
    
    st.plotly_chart(fig, use_container_width=True)

# 매매 내역 테이블
st.subheader("매매 내역")

if not df.empty:
    # 표시할 컬럼 선택 및 새 DataFrame 생성 (복사 대신)
    display_df = pd.DataFrame({
        '시간': df['timestamp'].dt.strftime('%Y-%m-%d %H:%M'),
        '결정': df['decision'].str.upper(),
        '비율(%)': df['percentage'],
        'BTC 가격(KRW)': df['btc_price'].apply(lambda x: f"{x:,.0f}"),
        'BTC 잔고': df['btc_balance'],
        'KRW 잔고': df['krw_balance'].apply(lambda x: f"{x:,.0f}"),
        '수익률(%)': df['profit_loss_pct'].apply(lambda x: f"{x:.2f}")
    })
    
    # 스타일링된 데이터프레임
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "결정": st.column_config.SelectboxColumn(
                width="small",
            ),
            "비율(%)": st.column_config.NumberColumn(
                format="%.1f%%",
                width="small",
            ),
            "수익률(%)": st.column_config.NumberColumn(
                format="%.2f%%",
                width="medium",
            ),
        }
    )

# 거래 상세 정보
st.subheader("최근 거래 상세 정보")

if not df.empty:
    # 탭 구성
    tab1, tab2 = st.tabs(["거래 세부사항", "AI 판단 이유"])
    
    with tab1:
        # 선택 메뉴
        selected_idx = st.selectbox("거래 선택:", 
                                     range(len(df)), 
                                     format_func=lambda i: f"{df.iloc[i]['timestamp'].strftime('%Y-%m-%d %H:%M')} - {df.iloc[i]['decision'].upper()}")
        
        selected_trade = df.iloc[selected_idx]
        
        # 거래 상세 정보
        st.markdown(f"""
        ### {selected_trade['timestamp'].strftime('%Y-%m-%d %H:%M')} 거래 세부사항
        
        **결정:** {selected_trade['decision'].upper()} {selected_trade['percentage']}%  
        **비트코인 가격:** ₩{selected_trade['btc_price']:,.0f}  
        **거래 후 BTC 잔고:** {selected_trade['btc_balance']:.8f} BTC  
        **거래 후 KRW 잔고:** ₩{selected_trade['krw_balance']:,.0f}  
        **포트폴리오 가치:** ₩{selected_trade['portfolio_value']:,.0f}  
        **수익률:** {selected_trade['profit_loss_pct']:.2f}%  
        """)
    
    with tab2:
        # 판단 이유 표시
        selected_idx2 = st.selectbox("AI 판단 선택:", 
                                     range(len(df)), 
                                     format_func=lambda i: f"{df.iloc[i]['timestamp'].strftime('%Y-%m-%d %H:%M')} - {df.iloc[i]['decision'].upper()}",
                                     key="reason_select")
        
        selected_trade2 = df.iloc[selected_idx2]
        
        st.markdown(f"### {selected_trade2['timestamp'].strftime('%Y-%m-%d %H:%M')} AI 판단 이유")
        st.write(selected_trade2['reason'])