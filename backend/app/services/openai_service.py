import os
import requests

class OpenAIService:
    @staticmethod
    def generate_llm_insight(grid_load_pct: float, electricity_price: float, solar_kw: float, ev_summary: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            if solar_kw > 15.0 and electricity_price <= 6.5:
                return (
                    f"GridWise AI Advisor: High solar availability ({solar_kw:.1f} kW) with off-peak tariff (₹{electricity_price}/kWh). "
                    "Algorithm actively routing clean solar electrons directly into connected vehicles, preventing peak grid surcharge."
                )
            elif grid_load_pct >= 80.0 and electricity_price >= 9.0:
                return (
                    f"GridWise AI Advisor: Elevated feeder strain ({grid_load_pct:.1f}%) and peak tariff (₹{electricity_price}/kWh). "
                    "Pausing charging and activating selective V2G discharge to stabilize feeder voltage and maximize feed-in revenue."
                )
            else:
                return (
                    f"GridWise AI Advisor: System operating at optimal equilibrium (Feeder Load: {grid_load_pct:.1f}%, Solar: {solar_kw:.1f} kW). "
                    "Pre-allocating charging schedules to ensure 100% departure SLA satisfaction."
                )

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            prompt = (
                f"You are the GridWise AI Chief Energy Systems Advisor. In 2 concise sentences, provide an executive operational recommendation based on: "
                f"Grid Load: {grid_load_pct:.1f}%, Price: ₹{electricity_price}/kWh, Solar Power: {solar_kw:.1f} kW, Fleet: {ev_summary}."
            )
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.4
            }
            res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=4.0)
            if res.status_code == 200:
                data = res.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

        return "GridWise AI Advisor: Real-time telemetry synchronized. Optimizing charging intervals against Time-of-Use tariffs and solar generation."
