import os
import json
import requests
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import python_bithumb
from openai import OpenAI
import time

# --- 추가된 부분: 색상 코드 정의 ---
class Colors:
    RESET = '\033[0m'  # 모든 색상 및 스타일 초기화
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    # 텍스트 색상
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # 밝은 텍스트 색상
    BRIGHT_BLACK = '\033[90m' # 회색
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

    # 배경 색상
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
# --- 여기까지 추가 ---


# .env 파일에서 API 키 로드
load_dotenv(override=True, verbose=True)
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# SQLite 데이터베이스 초기화 함수
def init_db():
    conn = sqlite3.connect('bitcoin_trading.db')
    c = conn.cursor()
    # 테이블 생성 시 percentage는 INTEGER로 유지, 실수로 저장될 일 없음
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

# DB 연결 가져오기 (현재는 execute_trade 내에서 init_db로 처리)
# def get_db_connection():
# return sqlite3.connect('bitcoin_trading.db')

# 뉴스 데이터 가져오는 함수
def get_bitcoin_news(api_key, query="bitcoin", location="us", language="en", num_results=5):
    params = {
        "engine": "google_news", "q": query, "gl": location,
        "hl": language, "api_key": api_key
    }
    api_url = "https://serpapi.com/search.json"
    news_data = []

    try:
        response = requests.get(api_url, params=params, timeout=10) # 타임아웃 추가
        response.raise_for_status() # HTTP 오류 발생 시 예외 발생
        results = response.json()

        if "news_results" in results:
            for news_item in results["news_results"][:num_results]:
                news_data.append({
                    "title": news_item.get("title"),
                    "date": news_item.get("date") # API 응답에 따라 snippet 등 다른 정보도 추가 가능
                })
    except requests.exceptions.RequestException as e:
        print(f"{Colors.YELLOW}Warning: Failed to get news data: {str(e)}{Colors.RESET}")
    return news_data


# AI 트레이딩 함수
def ai_trading():
    print(f"{Colors.BRIGHT_BLUE}Fetching chart and news data for AI analysis...{Colors.RESET}")
    # 차트 데이터 수집
    try:
        short_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute60", count=24)
        mid_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute240", count=30)
        long_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="day", count=30)
    except Exception as e:
        print(f"{Colors.BRIGHT_RED}Error fetching Bithumb chart data: {e}{Colors.RESET}")
        # 차트 데이터 실패 시 비어있는 DataFrame이나 None으로 처리하여 다음 로직에 영향 최소화
        return {"decision": "hold", "percentage": 0, "reason": f"Chart data fetch error: {e}"}


    # 뉴스 데이터 수집
    news_articles = []
    if SERPAPI_API_KEY:
        news_articles = get_bitcoin_news(SERPAPI_API_KEY, "bitcoin financial news OR bitcoin price news OR crypto market news", "us", "en", 7) # 뉴스 쿼리 구체화, 개수 증가
    else:
        print(f"{Colors.YELLOW}Warning: SERPAPI_API_KEY not found. Skipping news fetching.{Colors.RESET}")


    # 데이터 페이로드 준비
    # DataFrame이 None일 경우를 대비하여 to_json() 호출 전에 확인
    data_payload = {
        "short_term": json.loads(short_term_df.to_json(orient='records')) if short_term_df is not None else None,
        "mid_term": json.loads(mid_term_df.to_json(orient='records')) if mid_term_df is not None else None,
        "long_term": json.loads(long_term_df.to_json(orient='records')) if long_term_df is not None else None,
        "news": news_articles
    }

    # OpenAI GPT에게 판단 요청
    try:
        client = OpenAI() # API 키는 환경변수에서 자동 로드
        response = client.chat.completions.create(
            model="gpt-4o", # 또는 "gpt-3.5-turbo" 등 사용 가능한 모델
            messages=[
                {
                    "role": "system",
                    "content": """
                    You are an expert in Bitcoin investing, focusing on cautious, data-driven decisions.

                    You invest according to the following principles:
                    Rule No.1: Never lose money. (Minimize risk)
                    Rule No.2: Never forget Rule No.1. (Prioritize capital preservation)

                    Analyze the provided data:
                    1.  **Chart Data:** Multi-timeframe OHLCV data ('short_term': 1h, 'mid_term': 4h, 'long_term': daily).
                        Look for clear trend confirmations, support/resistance levels, and volume patterns.
                    2.  **News Data:** Recent Bitcoin news articles with 'title' and 'date'.
                        Evaluate sentiment (positive, negative, neutral) and potential market impact of significant news.

                    **Task:** Based on a CONSERVATIVE interpretation of BOTH technical analysis AND news sentiment/implications,
                    decide whether to **buy**, **sell**, or **hold** Bitcoin.
                    If market conditions are unclear or risky, prefer 'hold'.
                    For buy or sell decisions, suggest a conservative percentage (e.g., 5-25%) of available funds/BTC to use.
                    A 'hold' decision should always have percentage 0.

                    **Output Format:** Respond ONLY in JSON format like:
                    {"decision": "buy", "percentage": 10, "reason": "Clear breakout on 4h chart above key resistance, supported by positive regulatory news. Small position due to overall market volatility."}
                    {"decision": "sell", "percentage": 15, "reason": "Approaching strong resistance on daily chart with bearish divergence on RSI, and some FUD in recent news. Taking partial profits."}
                    {"decision": "hold", "percentage": 0, "reason": "Price in consolidation, mixed signals from indicators and news. Waiting for a clearer market direction."}
                    """
                },
                {
                    "role": "user",
                    "content": json.dumps(data_payload)
                }
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"{Colors.BRIGHT_RED}Error communicating with OpenAI: {e}{Colors.RESET}")
        result = {"decision": "hold", "percentage": 0, "reason": f"OpenAI API error: {e}"} # AI 오류 시 기본값

    return result


# 트레이딩 실행 함수
def execute_trade():
    # 데이터베이스 초기화
    conn = init_db()
    
    print(f"{Colors.BRIGHT_BLUE}--- Starting AI Trading Cycle ---{Colors.RESET}") # 정보성 메시지
    # AI 결정 얻기
    result = ai_trading()
    
    # AI의 전체 응답 (디버깅 또는 상세 분석용)
    print(f"{Colors.BRIGHT_BLACK}AI Raw Response: {json.dumps(result, indent=2)}{Colors.RESET}")
    
    # 빗썸 API 연결
    access = os.getenv("BITHUMB_ACCESS_KEY")
    secret = os.getenv("BITHUMB_SECRET_KEY")
    
    if not access or not secret:
        print(f"{Colors.BRIGHT_RED}### Bithumb API keys not found. Cannot proceed with live trading. ###{Colors.RESET}")
        # AI 결정이 있었더라도 API 키가 없어 거래 못함을 로그
        log_trade(conn, result.get('decision', 'ERROR_NO_KEYS'), 0, result.get('reason', "API keys missing, no trade possible"), 0, 0, 0)
        conn.close()
        return

    bithumb = python_bithumb.Bithumb(access, secret)

    # 잔고 확인
    my_krw, my_btc, current_price = 0.0, 0.0, 0.0 # 기본값 초기화
    try:
        my_krw = bithumb.get_balance("KRW")
        my_btc = bithumb.get_balance("BTC")
        current_price = python_bithumb.get_current_price("KRW-BTC")
        print(f"{Colors.CYAN}Initial KRW Balance: {my_krw:,.0f} KRW{Colors.RESET}")
        print(f"{Colors.CYAN}Initial BTC Balance: {my_btc:,.8f} BTC{Colors.RESET}")
        print(f"{Colors.CYAN}Current BTC Price: {current_price:,.0f} KRW{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.BRIGHT_RED}### Failed to get Bithumb balance/price: {str(e)} ###{Colors.RESET}")
        log_trade(conn, result.get('decision', 'ERROR_BITHUMB_API'), 0, result.get('reason', f"Bithumb API error: {str(e)}"), 0, 0, 0)
        conn.close()
        return

    # 결정 출력
    decision = result.get('decision', 'hold').upper() # 기본값 'hold'
    reason = result.get('reason', 'N/A')
    # AI가 percentage를 문자열로 줄 수도 있으니 int로 변환 시도
    try:
        percentage = int(result.get("percentage", 0))
    except ValueError:
        print(f"{Colors.YELLOW}Warning: AI returned non-integer percentage. Defaulting to 0.{Colors.RESET}")
        percentage = 0


    decision_color = Colors.BRIGHT_YELLOW # 기본값 (HOLD)
    if decision == "BUY":
        decision_color = Colors.BRIGHT_GREEN
    elif decision == "SELL":
        decision_color = Colors.BRIGHT_RED

    print(f"{decision_color}{Colors.BOLD}### AI Decision: {decision} ###{Colors.RESET}")
    print(f"{Colors.CYAN}### Reason: {reason} ###{Colors.RESET}")
    print(f"{Colors.CYAN}### Investment Percentage: {percentage}% ###{Colors.RESET}")
    
    order_executed = False
    final_decision_for_log = decision.lower() # 로그용 소문자 결정
    
    if decision == "BUY" and percentage > 0:
        krw_to_use = my_krw * (percentage / 100) 
        amount_krw_order = krw_to_use 
        
        if amount_krw_order >= 5000:  # 최소 주문액 5000원 이상
            print(f"{Colors.GREEN}### Buy Order Attempt: {amount_krw_order:,.0f} KRW worth of BTC ###{Colors.RESET}")
            try:
                order_result = bithumb.buy_market_order("KRW-BTC", amount_krw_order)
                print(f"{Colors.BRIGHT_GREEN}### Buy Order Success: {json.dumps(order_result)} ###{Colors.RESET}")
                order_executed = True
            except Exception as e:
                print(f"{Colors.BRIGHT_RED}### Buy Failed: {str(e)} ###{Colors.RESET}")
                final_decision_for_log = "buy_failed"
        else:
            print(f"{Colors.YELLOW}### Buy Order Skipped: Amount ({amount_krw_order:,.0f} KRW) below minimum 5000 KRW or 0% percentage ###{Colors.RESET}")
            final_decision_for_log = "buy_skipped"

    elif decision == "SELL" and percentage > 0:
        btc_to_sell = my_btc * (percentage / 100)
        
        if btc_to_sell * current_price >= 5000: # 최소 주문액 (원화 환산 가치) 5000원 이상
            print(f"{Colors.MAGENTA}### Sell Order Attempt: {btc_to_sell:,.8f} BTC ###{Colors.RESET}")
            try:
                order_result = bithumb.sell_market_order("KRW-BTC", btc_to_sell)
                print(f"{Colors.BRIGHT_MAGENTA}### Sell Order Success: {json.dumps(order_result)} ###{Colors.RESET}")
                order_executed = True
            except Exception as e:
                print(f"{Colors.BRIGHT_RED}### Sell Failed: {str(e)} ###{Colors.RESET}")
                final_decision_for_log = "sell_failed"
        else:
            print(f"{Colors.YELLOW}### Sell Order Skipped: Value ({btc_to_sell * current_price:,.0f} KRW) below minimum 5000 KRW or 0% percentage ###{Colors.RESET}")
            final_decision_for_log = "sell_skipped"

    elif decision == "HOLD" or percentage == 0: # HOLD거나 percentage가 0이면 관망
        print(f"{Colors.YELLOW}### Hold Position or 0% Percentage Action ###{Colors.RESET}")
        # 'hold'도 성공적인 결정 처리로 간주 (실제 거래는 없지만)
        # 만약 BUY/SELL인데 percentage가 0%여서 스킵된 경우도 이리로 올 수 있음.
        # final_decision_for_log는 이미 buy_skipped/sell_skipped로 설정되었을 수 있으므로 그대로 둠.
        # 만약 순수 HOLD면 final_decision_for_log는 'hold'가 됨.
        order_executed = True 
    
    # 잔고 업데이트를 위해 잠시 대기 (실제 거래소 반영 시간 고려)
    if order_executed and (decision == "BUY" or decision == "SELL") and percentage > 0 : # 실제 매수/매도가 있었을 경우
        print(f"{Colors.BRIGHT_BLUE}Waiting for order to reflect on balance...{Colors.RESET}")
        time.sleep(5) # API 상태에 따라 더 길게 필요할 수 있음
    else:
        time.sleep(1)
    
    # 거래 후 최신 잔고 조회 (또는 실패 시 이전 잔고 사용)
    updated_krw, updated_btc, updated_price = my_krw, my_btc, current_price # 기본값으로 이전 값 설정
    try:
        updated_krw = bithumb.get_balance("KRW")
        updated_btc = bithumb.get_balance("BTC")
        updated_price = python_bithumb.get_current_price("KRW-BTC") # 로깅 시점의 가격
        
        print(f"{Colors.BLUE}### Updated KRW Balance: {updated_krw:,.0f} KRW ###{Colors.RESET}")
        print(f"{Colors.BLUE}### Updated BTC Balance: {updated_btc:,.8f} BTC ###{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.BRIGHT_RED}### Failed to get updated Bithumb balance/price: {str(e)} ###{Colors.RESET}")
        # 에러 발생 시, 이미 이전 값으로 설정되어 있으므로 추가 작업 불필요

    # 거래 정보 로깅
    # order_executed는 실제 주문 API 호출 성공 여부가 아님. AI의 결정을 따랐는지 여부.
    # 실제 거래 성공/실패는 final_decision_for_log에 반영됨
    log_trade(
        conn,
        final_decision_for_log, 
        percentage if (final_decision_for_log == "buy" or final_decision_for_log == "sell") else 0, # 실제 거래 성공시에만 퍼센티지 기록
        reason,
        updated_btc,
        updated_krw, 
        updated_price
    )
    print(f"{Colors.BRIGHT_GREEN}Trade information logged to database.{Colors.RESET}")
    
    # 데이터베이스 연결 종료
    conn.close()
    print(f"{Colors.BRIGHT_BLUE}--- AI Trading Cycle Ended ---{Colors.RESET}")


# 실행
if __name__ == "__main__":
    # 무한 루프와 sleep 추가해서 주기적으로 실행하도록 수정 가능
    # while True:
    execute_trade()
    # time.sleep(3600) # 예: 1시간마다 실행