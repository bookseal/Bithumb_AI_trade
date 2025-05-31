import os
from dotenv import load_dotenv
load_dotenv(override=True, verbose=True)
import python_bithumb

def ai_trading():
    # 1. 빗썸 차트 데이터 가져오기 (30일 일봉)
    df = python_bithumb.get_ohlcv("KRW-BTC", interval="day", count=30)

    # 2. AI에게 데이터 제공하고 판단 받기
    from openai import OpenAI
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "You are an expert in Bitcoin investing. Tell me whether to buy, sell, or hold at the moment based on the chart data provided. response in json format.\n\nResponse Example:\n{\"decision\": \"buy\", \"reason\": \"some technical reason\"}\n{\"decision\": \"sell\", \"reason\": \"some technical reason\"}\n{\"decision\": \"hold\", \"reason\": \"some technical reason\"}"
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": df.to_json()
                    }
                ]
            }
        ],
        response_format={
            "type": "json_object"
        }
    )
    result = response.choices[0].message.content

    # 3. AI의 판단에 따라 실제로 자동매매 진행하기
    import json
    result = json.loads(result)
    access = os.getenv("BITHUMB_ACCESS_KEY")
    secret = os.getenv("BITHUMB_SECRET_KEY")
    bithumb = python_bithumb.Bithumb(access, secret)

    my_krw = bithumb.get_balance("KRW")
    my_btc = bithumb.get_balance("BTC")

    print("### AI Decision: ", result["decision"].upper(), "###")
    print(f"### Reason: {result['reason']} ###")
    
    if result["decision"] == "buy":
        if my_krw > 5000:
            print("### Buy Order Executed ###")
            bithumb.buy_market_order("KRW-BTC", my_krw*0.997)
        else:
            print("### Buy Order Failed: Insufficient KRW (less than 5000 KRW) ###")

    elif result["decision"] == "sell":
        current_price = python_bithumb.get_current_price("KRW-BTC")
        if my_btc * current_price > 5000:
            print("### Sell Order Executed ###")
            bithumb.sell_market_order("KRW-BTC", my_btc*0.997)
        else:
            print("### Sell Order Failed: Insufficient BTC (less than 5000 KRW worth) ###")

    elif result["decision"] == "hold":
        print("### Hold Position ###")

# import time
# while True:
#     time.sleep(10)
ai_trading()