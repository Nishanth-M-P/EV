import math
from typing import Dict, Any, List

class PriceSimulator:
    """
    Simulates dynamic Time-of-Use (TOU) electricity tariffs.
    Clearly labeled as: 'Simulated Electricity Price'.
    Categories:
    - Off-Peak (Low): Late night / early morning
    - Normal (Medium): Daytime baseline
    - Peak (High): Evening demand surge
    """
    LABEL = "Simulated Electricity Price"

    def __init__(self, currency: str = "INR (₹)", peak_multiplier: float = 1.0):
        self.currency = currency
        self.peak_multiplier = float(peak_multiplier)
        self.price_profile = self._generate_price_profile()

    def _generate_price_profile(self) -> List[float]:
        prices = []
        for h in range(24):
            if 0 <= h < 6 or h >= 23:
                # Off-peak: ~₹4.0 - ₹4.5 / kWh
                p = 4.0 + 0.3 * math.sin(h / 3.0)
            elif 6 <= h < 16:
                # Normal: ~₹6.0 - ₹7.2 / kWh
                p = 6.2 + 0.9 * math.sin((h - 6) / 10.0 * math.pi)
            else:
                # Peak (16:00 - 22:00): ~₹10.5 - ₹13.0 / kWh
                p = 10.5 + 2.5 * math.sin((h - 16) / 6.0 * math.pi) * self.peak_multiplier
            prices.append(round(p, 2))
        return prices

    def get_price_at_hour(self, hour: float) -> Dict[str, Any]:
        h_idx = int(hour) % 24
        next_idx = (h_idx + 1) % 24
        frac = hour - int(hour)
        price = self.price_profile[h_idx] * (1.0 - frac) + self.price_profile[next_idx] * frac
        price = round(price, 2)

        if price >= 9.5:
            category = "Peak"
        elif price <= 5.0:
            category = "Off-Peak"
        else:
            category = "Normal"

        return {
            "current_price": price,
            "value": price,
            "price_category": category,
            "currency": self.currency,
            "label": self.LABEL,
            "is_simulated": True
        }

    def get_24h_profile(self) -> List[float]:
        return self.price_profile
