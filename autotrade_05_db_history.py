import os
import json
import requests
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import python_bithumb
from openai import OpenAI
import time

# --- 색상 코드 정의 ---
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    # (이하 다른 색상 코드들은 이전과 동일하게 있다고 가정)
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
# --- 색상 코드 끝 ---

# .env 파일에서 API 키 로드
load_dotenv(override=True, verbose=True)
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
BITHUMB_ACCESS_KEY = os.getenv("BITHUMB_ACCESS_KEY") # ai_trading에서도 사용하기 위해 전역으로 로드
BITHUMB_SECRET_KEY = os.getenv("BITHUMB_SECRET_KEY") # ai_trading에서도 사용하기 위해 전역으로 로드

# SQLite 데이터베이스 초기화 함수
def init_db():
    conn = sqlite3.connect('bitcoin_trading.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  decision TEXT,
                  percentage INTEGER,
                  reason TEXT,
                  btc_balance REAL,
                  krw_balance REAL,
                  btc_price REAL)''')
    conn.commit()
    return conn

# 거래 정보를 DB에 기록하는 함수
def log_trade(conn, decision, percentage, reason, btc_balance, krw_balance, btc_price):
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("""INSERT INTO trades 
                 (timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_price) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_price))
    conn.commit()

# --- DB 연결 가져오기 함수 추가 ---
def get_db_connection():
    conn = sqlite3.connect('bitcoin_trading.db')
    # 만약 Row factory를 사용하고 싶다면 여기서 설정 가능 (결과를 dict로 바로 받기 등)
    # conn.row_factory = sqlite3.Row 
    return conn

# --- 최근 거래 내역 가져오기 함수 추가 ---
def get_recent_trades(limit=5):
    conn = get_db_connection()
    # 결과를 dictionary 형태로 받기 위해 row_factory 설정
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("""
    SELECT timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_price
    FROM trades
    ORDER BY timestamp DESC
    LIMIT ?
    """, (limit,))
    
    trades = [dict(row) for row in c.fetchall()] # 각 row를 dict로 변환
        
    conn.close()
    return trades

# 뉴스 데이터 가져오는 함수 (이전과 동일)
def get_bitcoin_news(api_key, query="bitcoin", location="us", language="en", num_results=5):
    params = {
        "engine": "google_news", "q": query, "gl": location,
        "hl": language, "api_key": api_key
    }
    api_url = "https://serpapi.com/search.json"
    news_data = []
    try:
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        results = response.json()
        if "news_results" in results:
            for news_item in results["news_results"][:num_results]:
                news_data.append({
                    "title": news_item.get("title"),
                    "date": news_item.get("date")
                })
    except requests.exceptions.RequestException as e:
        print(f"{Colors.YELLOW}Warning: Failed to get news data: {str(e)}{Colors.RESET}")
    return news_data

# --- AI 트레이딩 함수 수정 ---
def ai_trading():
    print(f"{Colors.BRIGHT_BLUE}Fetching data for AI analysis (Charts, News, Balance, Past Trades)...{Colors.RESET}")
    
    # 0. Bithumb API 준비 (잔고 및 현재가 조회용)
    current_balance_info = None
    my_krw, my_btc, current_price = 0.0, 0.0, 0.0 # 기본값

    if BITHUMB_ACCESS_KEY and BITHUMB_SECRET_KEY:
        try:
            bithumb_api_for_ai = python_bithumb.Bithumb(BITHUMB_ACCESS_KEY, BITHUMB_SECRET_KEY)
            my_krw = bithumb_api_for_ai.get_balance("KRW")
            my_btc = bithumb_api_for_ai.get_balance("BTC")
            current_price = python_bithumb.get_current_price("KRW-BTC")
            current_balance_info = {
                "krw": my_krw,
                "btc": my_btc,
                "current_btc_price_krw": current_price,
                "estimated_total_value_krw": my_krw + (my_btc * current_price)
            }
            print(f"{Colors.CYAN}AI Context: Current KRW: {my_krw:,.0f}, BTC: {my_btc:,.8f}, Price: {current_price:,.0f}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.YELLOW}Warning: AI context - Failed to get Bithumb balance/price: {str(e)}{Colors.RESET}")
            # 잔고 정보 없이 진행하거나, 기본값 사용
            current_balance_info = {"error": f"Failed to fetch live balance: {str(e)}"}
    else:
        print(f"{Colors.YELLOW}Warning: AI context - Bithumb API keys not configured. Balance info will be missing.{Colors.RESET}")
        current_balance_info = {"error": "API keys not configured for balance fetching."}

    # 1. 차트 데이터 수집
    short_term_df, mid_term_df, long_term_df = None, None, None # 초기화
    try:
        short_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute60", count=24*3) # 3일치 1시간봉
        mid_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute240", count=24*2) # 8일치 4시간봉
        long_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="day", count=60)       # 2달치 일봉
    except Exception as e:
        print(f"{Colors.BRIGHT_RED}Error fetching Bithumb chart data: {e}{Colors.RESET}")
        return {"decision": "hold", "percentage": 0, "reason": f"Critical error: Chart data fetch failed - {e}"}

    # 2. 뉴스 데이터 수집
    news_articles = []
    if SERPAPI_API_KEY:
        news_articles = get_bitcoin_news(SERPAPI_API_KEY, "bitcoin OR cryptocurrency OR crypto market sentiment", "us", "en", 7)
    else:
        print(f"{Colors.YELLOW}Warning: SERPAPI_API_KEY not found. Skipping news fetching.{Colors.RESET}")

    # 3. 최근 거래 내역 가져오기
    recent_trades = get_recent_trades(limit=10) # 최근 10건의 거래를 보도록 수정
    if recent_trades:
        print(f"{Colors.CYAN}AI Context: Fetched {len(recent_trades)} recent trade(s) for review.{Colors.RESET}")

    # 4. 데이터 페이로드 준비
    data_payload = {
        "chart_data": {
            "short_term_1h": json.loads(short_term_df.to_json(orient='records')) if short_term_df is not None else None,
            "mid_term_4h": json.loads(mid_term_df.to_json(orient='records')) if mid_term_df is not None else None,
            "long_term_daily": json.loads(long_term_df.to_json(orient='records')) if long_term_df is not None else None,
        },
        "news_articles": news_articles,
        "current_account_status": current_balance_info, # 이름 변경
        "recent_trade_history": recent_trades # 이름 변경
    }

    # 5. OpenAI GPT에게 판단 요청
    ai_decision_result = {"decision": "hold", "percentage": 0, "reason": "Default due to AI API error"} # 기본값
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o", # 또는 "gpt-4-turbo" 등
            messages=[
                {
                    "role": "system",
                    "content": """
                    You are an advanced AI Bitcoin trading strategist. Your primary goal is capital preservation, followed by profit generation.
                    Adhere to "Rule No.1: Never lose money. Rule No.2: Never forget Rule No.1."

                    You will receive data in several categories:
                    1.  `chart_data`: Multi-timeframe OHLCV data (1-hour, 4-hour, daily). Use this for technical analysis (trends, support/resistance, patterns, volume).
                    2.  `news_articles`: Recent Bitcoin/crypto news. Evaluate sentiment and potential market impact.
                    3.  `current_account_status`: Your current KRW and BTC balances, current BTC price in KRW, and total estimated value.
                    4.  `recent_trade_history`: A list of your recent trades, including decision, percentage, reason, and balances/price at that time.

                    **Your Task - Retrospective Analysis and Decision Making:**

                    A.  **Analyze `recent_trade_history` (Retrospection):**
                        * Profitability: Were past buy/sell decisions profitable given subsequent price movements? (Compare `btc_price` at trade time with current or later prices if inferable).
                        * Effectiveness: Did the market react as anticipated based on your `reason` for the trade?
                        * Market Change: Have overall market conditions (e.g., trend, volatility) significantly changed since the last few trades?
                        * Learning: Identify patterns from successful (e.g., bought at low, sold at high) or unsuccessful trades (e.g., bought at peak, sold at dip, premature exit/entry).
                        * Strategy Consistency: If a strategy was working, consider maintaining it. If it wasn't, identify why and consider adjustments. Avoid emotional reactions to single losses; look for patterns.

                    B.  **Analyze Current Market (`chart_data`, `news_articles`):**
                        * Technical Analysis: Identify current trends, key support/resistance levels, chart patterns, and volume across all timeframes.
                        * News Sentiment: Gauge the overall sentiment from news. Is it bullish, bearish, or neutral/mixed? Are there high-impact events?

                    C.  **Synthesize and Decide (Recursive Improvement):**
                        * Integrate insights from A (retrospection) and B (current market) with your `current_account_status`.
                        * Based on this comprehensive analysis, decide to **buy**, **sell**, or **hold** Bitcoin.
                        * If buying or selling, specify a `percentage` (integer, 1-100) of available KRW (for buying) or BTC (for selling). Be conservative (e.g., 5-30%) unless conviction is extremely high and supported by multiple factors including past successes with similar setups.
                        * A 'hold' decision must have `percentage: 0`.
                        * Provide a clear, concise `reason` that REFLECTS your analysis of past trades, current technicals, and news. For example: "Holding. Recent buy at similar level was premature. Waiting for stronger confirmation on daily chart despite positive short-term news." or "Buying 10%. Long-term uptrend strong, recent pullback held support, similar to a past profitable trade. News is neutral."

                    **Output Format (Strict JSON):**
                    {"decision": "buy", "percentage": 10, "reason": "Detailed reasoning based on retrospection, charts, and news."}
                    {"decision": "sell", "percentage": 15, "reason": "Detailed reasoning..."}
                    {"decision": "hold", "percentage": 0, "reason": "Detailed reasoning..."}
                    """
                },
                {
                    "role": "user",
                    "content": json.dumps(data_payload)
                }
            ],
            response_format={"type": "json_object"}
        )
        ai_decision_result = json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"{Colors.BRIGHT_RED}Error communicating with OpenAI: {e}{Colors.RESET}")
        # ai_decision_result는 이미 기본값으로 설정되어 있음
    
    return ai_decision_result


# --- 트레이딩 실행 함수 (색상 및 일부 로직 개선) ---
def execute_trade():
    conn = init_db()
    print(f"{Colors.BRIGHT_BLUE}--- Starting AI Trading Cycle ---{Colors.RESET}")
    
    ai_result = ai_trading() # AI 결정 (이제 과거 데이터 분석 포함)
    
    print(f"{Colors.BRIGHT_BLACK}AI Raw Response: {json.dumps(ai_result, indent=2)}{Colors.RESET}")
    
    if not BITHUMB_ACCESS_KEY or not BITHUMB_SECRET_KEY:
        print(f"{Colors.BRIGHT_RED}### Bithumb API keys not found. Cannot execute trades. ###{Colors.RESET}")
        log_trade(conn, ai_result.get('decision', 'ERROR_NO_KEYS'), 0, ai_result.get('reason', "API keys missing, no trade execution possible"), 0, 0, 0)
        conn.close()
        return

    bithumb_executor = python_bithumb.Bithumb(BITHUMB_ACCESS_KEY, BITHUMB_SECRET_KEY) # 거래 실행용 API 객체

    # 실제 거래 직전 최신 잔고/시세 확인
    exec_my_krw, exec_my_btc, exec_current_price = 0.0, 0.0, 0.0
    try:
        exec_my_krw = bithumb_executor.get_balance("KRW")
        exec_my_btc = bithumb_executor.get_balance("BTC")
        exec_current_price = bithumb_executor.get_current_price("KRW-BTC")
        print(f"{Colors.CYAN}Execute: Current KRW: {exec_my_krw:,.0f}, BTC: {exec_my_btc:,.8f}, Price: {exec_current_price:,.0f}{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.BRIGHT_RED}### Execute: Failed to get Bithumb balance/price: {str(e)} ###{Colors.RESET}")
        log_trade(conn, ai_result.get('decision', 'ERROR_BITHUMB_EXEC_API'), 0, ai_result.get('reason', f"Bithumb API error at execution: {str(e)}"), 0, 0, 0)
        conn.close()
        return

    # AI 결정 및 이유
    decision = ai_result.get('decision', 'hold').upper()
    reason = ai_result.get('reason', 'N/A')
    try:
        percentage = int(ai_result.get("percentage", 0))
        if not (0 <= percentage <= 100): # 퍼센티지 범위 검증
            print(f"{Colors.YELLOW}Warning: AI returned percentage out of range ({percentage}%). Clamping to 0-100.{Colors.RESET}")
            percentage = max(0, min(100, percentage))
    except ValueError:
        print(f"{Colors.YELLOW}Warning: AI returned non-integer percentage. Defaulting to 0.{Colors.RESET}")
        percentage = 0

    decision_color = Colors.BRIGHT_YELLOW
    if decision == "BUY": decision_color = Colors.BRIGHT_GREEN
    elif decision == "SELL": decision_color = Colors.BRIGHT_RED

    print(f"{decision_color}{Colors.BOLD}### AI Decision: {decision} ({percentage}%) ###{Colors.RESET}")
    print(f"{Colors.CYAN}### Reason: {reason} ###{Colors.RESET}")
    
    order_executed_successfully = False # 실제 주문 성공 여부
    final_decision_for_log = decision.lower() # 로그용 기본 결정 (실패 시 변경)
    
    if decision == "BUY" and percentage > 0:
        krw_to_use_for_buy = exec_my_krw * (percentage / 100)
        if krw_to_use_for_buy >= 5000:
            print(f"{Colors.GREEN}### Buy Order Attempt: {krw_to_use_for_buy:,.0f} KRW worth of BTC ###{Colors.RESET}")
            try:
                order_feedback = bithumb_executor.buy_market_order("KRW-BTC", krw_to_use_for_buy)
                print(f"{Colors.BRIGHT_GREEN}### Buy Order Success: {json.dumps(order_feedback)} ###{Colors.RESET}")
                order_executed_successfully = True
            except Exception as e:
                print(f"{Colors.BRIGHT_RED}### Buy Failed: {str(e)} ###{Colors.RESET}")
                final_decision_for_log = "buy_failed"
        else:
            print(f"{Colors.YELLOW}### Buy Order Skipped: Amount ({krw_to_use_for_buy:,.0f} KRW) < 5000 KRW or Percentage is 0.{Colors.RESET}")
            final_decision_for_log = "buy_skipped"

    elif decision == "SELL" and percentage > 0:
        btc_to_sell_amount = exec_my_btc * (percentage / 100)
        if btc_to_sell_amount * exec_current_price >= 5000:
            print(f"{Colors.MAGENTA}### Sell Order Attempt: {btc_to_sell_amount:,.8f} BTC ###{Colors.RESET}")
            try:
                order_feedback = bithumb_executor.sell_market_order("KRW-BTC", btc_to_sell_amount)
                print(f"{Colors.BRIGHT_MAGENTA}### Sell Order Success: {json.dumps(order_feedback)} ###{Colors.RESET}")
                order_executed_successfully = True
            except Exception as e:
                print(f"{Colors.BRIGHT_RED}### Sell Failed: {str(e)} ###{Colors.RESET}")
                final_decision_for_log = "sell_failed"
        else:
            print(f"{Colors.YELLOW}### Sell Order Skipped: Value ({btc_to_sell_amount * exec_current_price:,.0f} KRW) < 5000 KRW or Percentage is 0.{Colors.RESET}")
            final_decision_for_log = "sell_skipped"

    elif decision == "HOLD" or percentage == 0:
        print(f"{Colors.YELLOW}### Hold Position or 0% Percentage Action ###{Colors.RESET}")
        # final_decision_for_log는 'hold' 또는 이미 설정된 'buy_skipped'/'sell_skipped' 유지
        order_executed_successfully = True # 결정은 따랐으므로 true (실제 주문 성공과는 다름)

    # 잔고 업데이트 대기
    if order_executed_successfully and (decision == "BUY" or decision == "SELL") and percentage > 0:
        print(f"{Colors.BRIGHT_BLUE}Waiting for order to reflect on balance...{Colors.RESET}")
        time.sleep(5) 
    else:
        time.sleep(1)
    
    # 거래 후 최신 잔고/시세 조회
    updated_krw, updated_btc, updated_price = exec_my_krw, exec_my_btc, exec_current_price # 기본값
    try:
        updated_krw = bithumb_executor.get_balance("KRW")
        updated_btc = bithumb_executor.get_balance("BTC")
        updated_price = python_bithumb.get_current_price("KRW-BTC") # 현재 시세는 라이브러리 직접 호출

        print(f"{Colors.BLUE}### Updated KRW Balance: {updated_krw:,.0f} KRW ###{Colors.RESET}")
        print(f"{Colors.BLUE}### Updated BTC Balance: {updated_btc:,.8f} BTC ###{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.BRIGHT_RED}### Failed to get updated Bithumb balance/price: {str(e)} ###{Colors.RESET}")

    # 거래 정보 로깅
    log_trade(
        conn,
        final_decision_for_log, 
        percentage if order_executed_successfully and (decision == "BUY" or decision == "SELL") else 0,
        reason,
        updated_btc,
        updated_krw, 
        updated_price
    )
    print(f"{Colors.BRIGHT_GREEN}Trade information logged to database.{Colors.RESET}")
    
    conn.close()
    print(f"{Colors.BRIGHT_BLUE}--- AI Trading Cycle Ended ---{Colors.RESET}\n")

# 실행
if __name__ == "__main__":
    # 주기적으로 실행하려면 아래 주석 해제
    # while True:
    execute_trade()
    # print(f"{Colors.BOLD}{Colors.BRIGHT_YELLOW}Sleeping for 1 hour...{Colors.RESET}")
    # time.sleep(3600) # 예: 1시간마다 실행