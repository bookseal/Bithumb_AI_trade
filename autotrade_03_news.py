import os
import json
import requests  # 뉴스 수집용
from dotenv import load_dotenv
import python_bithumb # 빗썸 데이터 수집용
from openai import OpenAI # OpenAI API 사용

# .env 파일에서 API 키 로드
load_dotenv(override=True, verbose=True)
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# 뉴스 데이터 가져오는 함수
def get_bitcoin_news(api_key, query="bitcoin", location="us", language="en", num_results=5):
    """
    SerpAPI를 사용하여 Google News에서 뉴스 기사의 제목과 날짜를 가져옵니다.
    """
    params = {
        "engine": "google_news", "q": f"{query} when:3d", "gl": location,
        "hl": language, "api_key": api_key
    }
    api_url = "https://serpapi.com/search.json"
    news_data = []

    response = requests.get(api_url, params=params)
    response.raise_for_status() # 기본적인 HTTP 오류는 확인
    results = response.json()

    if "news_results" in results:
        for news_item in results["news_results"][:num_results]:
            news_data.append({
                "title": news_item.get("title"),
                "date": news_item.get("date")
            })
    return news_data

# AI 트레이딩 함수 (오류 처리 제거)
def ai_trading():
    """
    차트/뉴스 데이터 수집 및 OpenAI 분석 요청
    """
    # 1. 멀티 타임프레임 차트 데이터 수집 (Bithumb)
    short_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute60", count=24)
    mid_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute240", count=30)
    long_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="day", count=30)

    # 2. 최신 뉴스 데이터 수집 (SerpAPI)
    news_articles = []
    if SERPAPI_API_KEY: # 키가 있을 때만 호출 시도
        news_articles = get_bitcoin_news(
            api_key=SERPAPI_API_KEY, query="bitcoin news",
            location="us", language="en", num_results=5
        )

    # 3. 데이터 페이로드 준비
    data_payload = {
        "short_term": json.loads(short_term_df.to_json()) if short_term_df is not None else None,
        "mid_term": json.loads(mid_term_df.to_json()) if mid_term_df is not None else None,
        "long_term": json.loads(long_term_df.to_json()) if long_term_df is not None else None,
        "news": news_articles
    }

    # 4. OpenAI GPT에게 판단 요청
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
                1.  **Chart Data:** Multi-timeframe OHLCV data ('short_term': 1h, 'mid_term': 4h, 'long_term': daily). Use this for technical analysis.
                2.  **News Data:** A list of recent Bitcoin news articles under the 'news' key, each containing 'title' and 'date'. Evaluate sentiment and potential market impact.

                **Task:** Based on BOTH technical analysis AND news sentiment/implications, decide whether to **buy**, **sell**, or **hold** Bitcoin.

                **Output Format:** Respond ONLY in JSON format like the examples below.

                Example (Buy): {"decision": "buy", "reason": "Price broke resistance (4h chart), supported by positive institutional adoption news."}
                Example (Sell): {"decision": "sell", "reason": "Bearish divergence (daily chart), combined with negative regulatory news."}
                Example (Hold): {"decision": "hold", "reason": "Consolidating price action, mixed news signals. Waiting for confirmation."}
                """
            },
            {
                "role": "user",
                "content": json.dumps(data_payload, separators=(',', ':'))
            }
        ],
        response_format={"type": "json_object"}
    )

    # 5. AI 응답 처리
    result = json.loads(response.choices[0].message.content)
    return result

trading_decision = ai_trading()
print(json.dumps(trading_decision, indent=4, ensure_ascii=False))