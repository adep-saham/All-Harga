import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
from typing import Tuple

URL_STARGOLD = "https://stargold.id/price/"


def _to_int(text: str) -> int:
    if not text:
        return 0
    text = (
        text.replace("Rp", "")
        .replace(".", "")
        .replace(",", "")
        .replace("*", "")
        .strip()
    )
    return int(text) if text.isdigit() else 0


def _to_float(text: str) -> float:
    if not text:
        return 0.0
    text = text.replace(",", ".").strip()
    try:
        return float(text)
    except:
        return 0.0


def parse_stargold(_: str = "") -> Tuple[pd.DataFrame, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    r = requests.get(URL_STARGOLD, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    wrappers = soup.find_all("div", class_="compare-page-wrapper")
    if not wrappers:
        raise ValueError("StarGold: blok harga tidak ditemukan.")

    records = []

    # =====================================================
    # LOOP SEMUA VENDOR
    # =====================================================
    for wrap in wrappers:
        title = wrap.find("h2", class_="title")
        table = wrap.find("table")

        if not title or not table:
            continue

        vendor_name = title.get_text(strip=True)

        rows = table.find_all("tr")[1:]  # skip header
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            berat_txt = tds[0].get_text(strip=True)
            jual_txt = tds[1].get_text(strip=True)
            buy_txt = tds[2].get_text(strip=True)

            weight = _to_float(berat_txt)
            sell = _to_int(jual_txt)
            buyback = _to_int(buy_txt)

            if weight > 0 and sell > 0:
                records.append({
                    "vendor": vendor_name,
                    "weight_g": weight,
                    "sell_idr": sell,
                    "buyback_idr": buyback,
                    "stock": "Ready"
                })

    if not records:
        raise ValueError("StarGold: data kosong setelah parsing.")

    df = (
        pd.DataFrame(records)
        .sort_values(["vendor", "weight_g"])
        .reset_index(drop=True)
    )

    return df, "StarGold (All Vendors)"
