import requests
import pandas as pd
import re
from bs4 import BeautifulSoup
from typing import Tuple

URL_AGUNG = "https://agungjewellery.com/harga-lm-2/"


# =========================
# HELPERS
# =========================
def _clean_rp(text: str) -> int:
    if not text:
        return 0
    return int(re.sub(r"[^\d]", "", text) or 0)


def _extract_weight(text: str) -> float:
    """
    '0.5 gr (Certicard)' -> 0.5
    '100gr (Certicard) RM#' -> 100
    """
    if not text:
        return 0.0
    text = text.lower().replace(",", ".")
    m = re.search(r"([\d\.]+)\s*gr", text)
    return float(m.group(1)) if m else 0.0


# =========================
# MAIN
# =========================
def parse_agungjewellery() -> Tuple[pd.DataFrame, str]:
    resp = requests.get(
        URL_AGUNG,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1️⃣ TABEL FIX BERDASARKAN HTML ASLI
    table = soup.find("table", id="table_17973856")
    if not table:
        raise ValueError("Tabel harga Agung Jewellery tidak ditemukan.")

    tbody = table.find("tbody")
    if not tbody:
        raise ValueError("Tbody tabel tidak ditemukan.")

    records = []

    # 2️⃣ LOOP BARIS
    for row in tbody.find_all("tr"):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) != 3:
            continue

        pecahan, harga_jual, harga_buyback = cols

        # 🔒 FILTER PALING PENTING
        if "(certicard)" not in pecahan.lower():
            continue
        if "non rm" in pecahan.lower():
            continue

        weight = _extract_weight(pecahan)
        sell = _clean_rp(harga_jual)
        buyback = _clean_rp(harga_buyback)

        if weight > 0 and sell > 0 and buyback > 0:
            records.append({
                "vendor": "Agung Jewellery",
                "weight_g": weight,
                "sell_idr": sell,
                "buyback_idr": buyback,
                "stock": "Ready"
            })

    if not records:
        raise ValueError("Data harga Agung Jewellery kosong setelah parsing.")

    df = pd.DataFrame(records)

    # 3️⃣ SORT FINAL
    df = (
        df.sort_values("weight_g")
          .reset_index(drop=True)
    )

    label = "Agung Jewellery (LM Certicard)"

    return df, label
