import requests
import pandas as pd
import re
import json
from typing import Tuple


URL_STARGOLD = "https://stargold.id/price/"


def parse_stargold(_: str = "") -> Tuple[pd.DataFrame, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    r = requests.get(URL_STARGOLD, headers=headers, timeout=30)
    r.raise_for_status()
    html = r.text

    # =====================================================
    # 1. Cari JSON di window.__NUXT__
    # =====================================================
    m = re.search(r"window\.__NUXT__\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        raise ValueError("StarGold: tidak menemukan data JSON (__NUXT__).")

    raw_json = m.group(1)

    try:
        data = json.loads(raw_json)
    except Exception as e:
        raise ValueError(f"StarGold: gagal parse JSON (__NUXT__): {e}")

    # =====================================================
    # 2. Navigasi struktur (robust)
    # =====================================================
    prices = None

    def find_prices(obj):
        nonlocal prices
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("prices", "priceList", "products"):
                    prices = v
                    return
                find_prices(v)
        elif isinstance(obj, list):
            for i in obj:
                find_prices(i)

    find_prices(data)

    if not prices or not isinstance(prices, list):
        raise ValueError("StarGold: tidak menemukan blok harga (prices).")

    # =====================================================
    # 3. Mapping ke schema app
    # =====================================================
    records = []

    for item in prices:
        try:
            weight = float(item.get("weight", 0))
            sell = int(item.get("sell_price", 0))
            buy = int(item.get("buyback_price", 0))
        except Exception:
            continue

        if weight > 0 and sell > 0:
            records.append({
                "vendor": "StarGold",
                "weight_g": weight,
                "sell_idr": sell,
                "buyback_idr": buy,
                "stock": "Ready"
            })

    if not records:
        raise ValueError("StarGold: data harga kosong setelah parsing JSON.")

    df = (
        pd.DataFrame(records)
        .drop_duplicates(subset="weight_g")
        .sort_values("weight_g")
        .reset_index(drop=True)
    )

    return df, "StarGold"
