import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
from typing import Tuple


URL = "https://stargold.id/price/"


def _to_int(text: str) -> int:
    if not text:
        return 0
    text = text.replace("Rp", "").replace(".", "").replace(",", "").strip()
    return int(text) if text.isdigit() else 0


def parse_stargold(_: str = "") -> Tuple[pd.DataFrame, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # =====================================================
    # 1. Cari section STARGOLD
    # =====================================================
    title = soup.find("h2", string=re.compile(r"STARGOLD", re.I))
    if not title:
        raise ValueError("StarGold: judul STARGOLD tidak ditemukan.")

    table = title.find_parent("div", class_="compare-page-wrapper") \
                 .find("table")

    if not table:
        raise ValueError("StarGold: tabel harga tidak ditemukan.")

    # =====================================================
    # 2. Parse baris
    # =====================================================
    rows = table.find_all("tr")[1:]  # skip header

    records = []

    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) != 3:
            continue

        berat = tds[0].get_text(strip=True)
        jual = tds[1].get_text(strip=True)
        buyback = tds[2].get_text(strip=True)

        try:
            weight = float(berat)
        except:
            continue

        records.append({
            "vendor": "StarGold",
            "weight_g": weight,
            "sell_idr": _to_int(jual),
            "buyback_idr": _to_int(buyback),
            "stock": "Ready"
        })

    if not records:
        raise ValueError("StarGold: data kosong setelah parsing.")

    df = (
        pd.DataFrame(records)
        .sort_values("weight_g")
        .reset_index(drop=True)
    )

    return df, "StarGold"
