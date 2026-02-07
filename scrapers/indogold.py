# scrapers/indogold.py
import json
import re
import requests
import pandas as pd
from datetime import datetime

URL_INDOGOLD = "https://www.indogold.id/harga-emas-hari-ini"
API = "https://www.indogold.id/home/get_data_pricelist"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "*/*",
    "Origin": "https://www.indogold.id",
    "Referer": URL_INDOGOLD,
}


def _idr(x: str) -> int:
    return int(re.sub(r"[^\d]", "", x)) if x else 0


def parse_indogold():
    session = requests.Session()

    files = {
        "form": (None, json.dumps({"product": "comparison_antamxubs"}), "application/json"),
    }

    r = session.post(API, headers=HEADERS, files=files, timeout=30)
    r.raise_for_status()
    payload = r.json()

    rows = []
    denom = payload["data"]["data_denom"]

    for weight, brands in denom.items():
        w = float(weight)
        for brand in ["UBS", "Antam"]:
            b = brands.get(brand)
            if not b:
                continue

            sell = _idr(b.get("harga"))
            buyback = _idr(b.get("harga_buyback"))

            # Perbandingan
            rows.append({
                "vendor": f"Perbandingan - {brand}",
                "weight_g": w,
                "sell_idr": sell,
                "buyback_idr": buyback,
            })

            # Single brand
            rows.append({
                "vendor": brand,
                "weight_g": w,
                "sell_idr": sell,
                "buyback_idr": buyback,
            })

    df = pd.DataFrame(rows)

    df = (
        df.sort_values(["vendor", "weight_g"])
          .groupby(["vendor", "weight_g"], as_index=False)
          .agg({"sell_idr": "max", "buyback_idr": "max"})
    )

    label = f"IndoGold — API(JSON) — Last Update: {datetime.now().strftime('%d %B %Y %H:%M')}"

    return df, label
