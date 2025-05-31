import os
import json
import requests
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import python_bithumb
from openai import OpenAI
import time

# .env 파일에서 API 키 로드
load_dotenv(override=True, verbose=True)
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

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

# DB 연결 가져오기
def get_db_connection():
    return sqlite3.connect('bitcoin_trading.db')

# 뉴스 데이터 가져오는 함수
def get_bitcoin_news(api_key, query="bitcoin", location="us", language="en", num_results=5):
    params = {
        "engine": "google_news", "q": query, "gl": location,
        "hl": language, "api_key": api_key
    }
    api_url = "https://serpapi.com/search.json"
    news_data = []

    response = requests.get(api_url, params=params)
    response.raise_for_status()
    results = response.json()

    if "news_results" in results:
        for news_item in results["news_results"][:num_results]:
            news_data.append({
                "title": news_item.get("title"),
                "date": news_item.get("date")
            })
    return news_data

# AI 트레이딩 함수
def ai_trading():
    # 차트 데이터 수집
    short_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute60", count=24)
    mid_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute240", count=30)
    long_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="day", count=30)

    # 뉴스 데이터 수집
    news_articles = []
    if SERPAPI_API_KEY:
        news_articles = get_bitcoin_news(SERPAPI_API_KEY, "bitcoin news", "us", "en", 5)

    # 데이터 페이로드 준비
    data_payload = {
        "short_term": json.loads(short_term_df.to_json()) if short_term_df is not None else None,
        "mid_term": json.loads(mid_term_df.to_json()) if mid_term_df is not None else None,
        "long_term": json.loads(long_term_df.to_json()) if long_term_df is not None else None,
        "news": news_articles
    }

    # OpenAI GPT에게 판단 요청
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": """
                You are an expert in Bitcoin investing.

                You invest according to the following principles:
                Rule No.1: Never lose money.
                Rule No.2: Never forget Rule No.1.

                Analyze the provided data:
                1.  **Chart Data:** Multi-timeframe OHLCV data ('short_term': 1h, 'mid_term': 4h, 'long_term': daily).
                2.  **News Data:** Recent Bitcoin news articles with 'title' and 'date'.

                **Task:** Based on technical analysis and news sentiment, decide whether to **buy**, **sell**, or **hold** Bitcoin.
                For buy or sell decisions, include a percentage (1-100) indicating what portion of available funds to use.

                **Output Format:** Respond ONLY in JSON format like:
                {"decision": "buy", "percentage": 20, "reason": "some technical reason"}
                {"decision": "sell", "percentage": 50, "reason": "some technical reason"}
                {"decision": "hold", "percentage": 0, "reason": "some technical reason"}
                """
            },
            {
                "role": "user",
                "content": json.dumps(data_payload)
            }
        ],
        response_format={"type": "json_object"}
    )

    # AI 응답 처리
    result = json.loads(response.choices[0].message.content)
    return result

# 트레이딩 실행 함수
def execute_trade():
    # 데이터베이스 초기화
    conn = init_db()
    
    # AI 결정 얻기
    result = ai_trading()
    print(result)
    
    # 빗썸 API 연결
    access = os.getenv("BITHUMB_ACCESS_KEY")
    secret = os.getenv("BITHUMB_SECRET_KEY")
    bithumb = python_bithumb.Bithumb(access, secret)

    # 잔고 확인
    my_krw = bithumb.get_balance("KRW")
    my_btc = bithumb.get_balance("BTC")
    current_price = python_bithumb.get_current_price("KRW-BTC")

    # 결정 출력
    print(f"### AI Decision: {result['decision'].upper()} ###")
    print(f"### Reason: {result['reason']} ###")
    
    # 투자 비율 (0-100%)
    percentage = result.get("percentage", 0)
    print(f"### Investment Percentage: {percentage}% ###")
    
    order_executed = False
    
    if result["decision"] == "buy":
        amount = my_krw * (percentage / 100) * 0.997  # 수수료 고려
        
        if amount > 5000:  # 최소 주문액 확인
            print(f"### Buy Order: {amount:,.0f} KRW ###")
            try:
                bithumb.buy_market_order("KRW-BTC", amount)
                order_executed = True
            except Exception as e:
                print(f"### Buy Failed: {str(e)} ###")
        else:
            print(f"### Buy Failed: Amount ({amount:,.0f} KRW) below minimum ###")

    elif result["decision"] == "sell":
        btc_amount = my_btc * (percentage / 100) * 0.997  # 수수료 고려
        value = btc_amount * current_price
        
        if value > 5000:  # 최소 주문액 확인
            print(f"### Sell Order: {btc_amount} BTC ###")
            try:
                bithumb.sell_market_order("KRW-BTC", btc_amount)
                order_executed = True
            except Exception as e:
                print(f"### Sell Failed: {str(e)} ###")
        else:
            print(f"### Sell Failed: Value ({value:,.0f} KRW) below minimum ###")

    elif result["decision"] == "hold":
        print("### Hold Position ###")
        order_executed = True  # 'hold'도 성공한 결정으로 간주
    
    # 잔고 업데이트를 위해 잠시 대기
    time.sleep(1)
    
    # 거래 후 최신 잔고 조회
    updated_krw = bithumb.get_balance("KRW")
    updated_btc = bithumb.get_balance("BTC")
    updated_price = python_bithumb.get_current_price("KRW-BTC")
    
    print(f"### Updated KRW Balance: {updated_krw:,.0f} KRW ###")
    print(f"### Updated BTC Balance: {updated_btc:,.8f} BTC ###")
    
    # 거래 정보 로깅
    log_trade(
        conn,
        result["decision"],
        percentage if order_executed else 0,
        result["reason"],
        updated_btc,
        updated_krw, 
        updated_price
    )
    
    # 데이터베이스 연결 종료
    conn.close()

# 실행
if __name__ == "__main__":
    execute_trade()