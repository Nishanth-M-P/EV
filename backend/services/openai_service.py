import os
import requests
from typing import Optional

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

class OpenAIService:
    """
    Secure backend service for OpenAI LLM explainability and strategic energy insights.
    Secret key is safely kept in environment variables and never committed to source control.
    """
    @staticmethod
    def generate_llm_insight(grid_load_pct: float, electricity_price: float, solar_kw: float, ev_summary: str) -> Optional[str]:
        if not OPENAI_API_KEY:
            return None
        
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            prompt = (
                f"You are GridWise AI Energy Advisor. Given grid load={grid_load_pct}%, tariff=₹{electricity_price}/kWh, "
                f"solar={solar_kw}kW, and fleet status: {ev_summary}. Provide a 1-sentence strategic AI recommendation for grid stabilization."
            )
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 60,
                "temperature": 0.3
            }
            res = requests.post(url, headers=headers, json=payload, timeout=3.0)
            if res.status_code == 200:
                data = res.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
        return None
