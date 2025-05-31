import os
import json
import requests  # 뉴스 수집용
from dotenv import load_dotenv
import python_bithumb # 빗썸 데이터 수집용
from openai import OpenAI # OpenAI API 사용

# .env 파일에서 API 키 로드
load_dotenv(override=True)
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# 뉴스 데이터 가져오는 함수
def get_bitcoin_news(api_key, query="bitcoin", location="us", language="en", num_results=5):
    """
    SerpAPI를 사용하여 Google News에서 뉴스 기사의 제목과 날짜를 가져옵니다.
    """
    params = {
        "engine": "google_news", "q": query, "gl": location,
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

print(get_bitcoin_news(SERPAPI_API_KEY))