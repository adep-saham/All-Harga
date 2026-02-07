import requests
import pandas as pd
from datetime import datetime

URL_HRTA = "https://hrtagold.id/en/gold-price"
API_HRTA_DAILY = "https://hrtagold.id/api/v1/brandings/price/daily"


def parse_hrta(_: str = "") -> tuple[pd.DataFrame, str]:
    headers = {
        "accept": "application/json",
        "user-agent": "Mozilla/5.0",
        "referer": URL_HRTA,
        "cache-control": "no-cache",
        "pragma": "no-cache",
    }

    r = requests.get(API_HRTA_DAILY, headers=headers, timeout=30)
    r.raise_for_status()
    js = r.json()

    if "data" not in js:
        raise RuntimeError(f"HRTA API error: key 'data' not found. Keys={list(js.keys())}")

    rows = []

    for block in js["data"]:
        series = block.get("series", "HRTA").upper()
        prices = block.get("prices", [])

        for p in prices:
            rows.append({
                "snapshot_ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "update_label": js.get("updated_date"),
                "source_site": "hrta",
                "vendor": f"HRTA {series}",
                "weight_g": float(p.get("gramasi")),
                "sell_idr": int(p.get("price", 0)),
                "buyback_idr": int(p.get("buyback_price", 0)),
                "source_url": URL_HRTA,
            })

    if not rows:
        raise RuntimeError("HRTA API: data kosong")

    df = pd.DataFrame(rows)

    # urutkan vendor lalu berat
    df = df.sort_values(["vendor", "weight_g"])

    return df, f"HRTA API Updated {js.get('updated_date')}"
