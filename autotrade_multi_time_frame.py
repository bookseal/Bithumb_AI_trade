# Import necessary libraries
import os
import json
import time
from dotenv import load_dotenv 
import python_bithumb      
from openai import OpenAI  

load_dotenv(override=True, verbose=True)

def ai_trading():
    # 1. Collect multi-timeframe data for KRW-BTC pair
    # Short-term: 24 candles of 1-hour intervals
    short_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute60", count=24)
    # Mid-term: 30 candles of 4-hour (240 minutes) intervals
    mid_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="minute240", count=30)
    # Long-term: 30 candles of daily intervals
    long_term_df = python_bithumb.get_ohlcv("KRW-BTC", interval="day", count=30)

    # 2. Convert pandas DataFrames to JSON format for the API payload
    # The .to_json() method from pandas DataFrame returns a JSON string.
    # json.loads() then parses this string back into a Python dictionary (or list of dictionaries for 'records' orient, etc.).
    # This ensures the data is in a standard JSON structure before being wrapped into the final payload.
    data_payload = {
        "short_term": json.loads(short_term_df.to_json(orient='records')), # Using 'records' orient for a list of dicts
        "mid_term": json.loads(mid_term_df.to_json(orient='records')),   # Using 'records' orient for a list of dicts
        "long_term": json.loads(long_term_df.to_json(orient='records'))    # Using 'records' orient for a list of dicts
    }

    # 3. Request a trading decision from OpenAI GPT
    client = OpenAI() # Initialize the OpenAI client (API key is typically read from OPENAI_API_KEY environment variable)

    response = client.chat.completions.create(
        model="gpt-4o", # Specify the model to use
        messages=[
            {
                "role": "system", # System message defines the AI's role and instructions
                "content": """
                You are an expert in Bitcoin investing.

                You invest according to the following principles:
                Rule No.1: Never lose money.
                Rule No.2: Never forget Rule

                Use multi-timeframe analysis based on the chart data provided:
                - short_term: 1-hour candles
                - mid_term: 4-hour candles
                - long_term: daily candles

                Tell me whether to buy, sell, or hold at the moment.
                Respond in JSON format like this:
                {"decision": "buy", "reason": "some technical reason"}
                {"decision": "sell", "reason": "some technical reason"}
                {"decision": "hold", "reason": "some technical reason"}
                """
            },
            {
                "role": "user", # User message provides the data for the AI to analyze
                "content": json.dumps(data_payload) # Convert the Python dictionary payload to a JSON string
            }
        ],
        response_format={ # Ensure the response from the API is a JSON object
            "type": "json_object"
        }
    )

    # 4. Process the AI's response
    # The response from the AI is a JSON string, parse it into a Python dictionary
    result = json.loads(response.choices[0].message.content)
    return result

# Call the function and print the result
print(ai_trading())