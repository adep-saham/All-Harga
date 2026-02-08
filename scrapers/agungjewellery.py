import requests
import pandas as pd
import re
from bs4 import BeautifulSoup
from typing import Tuple

URL_AGUNG = "https://agungjewellery.com/harga-lm-2/"


# =====================================================
# HELPERS
# =====================================================
def _clean_rp(x: str) -> int:
    """ '1.715.000' -> 1715000 """
    if not x:
        return 0
    return int(re.sub(r"[^\d]", "", x) or 0)


def _extract_weight(text: str) -> float:
    """
    '0.5 gr (Certicard)' -> 0.5
    '100gr (Certicard) RM#' -> 100
    """
    if not text:
        return 0.0
    text = text.lower()
    text = text.replace(",", ".")
    m = re.search(r"([\d\.]+)\s*gr", text)
    return float(m.group(1)) if m else 0.0


# =====================================================
# MAIN PARSER
# =====================================================
def parse_agungjewellery() -> Tuple[pd.DataFrame, str]:
    resp = requests.get(URL_AGUNG, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # =================================================
    # 1. Ambil tabel LM (ID FIX)
    # =================================================
    table = soup.find("table", id="table_17973856")
    if not table:
        raise ValueError("Tabel harga Agung Jewellery tidak ditemukan.")

    rows = table.find("tbody").find_all("tr")

    records = []

    # =================================================
    # 2. Loop baris & FILTER LM CERTICARD
    # =================================================
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) != 3:
            continue

        pecahan, harga_jual, harga_buyback = cols

        # 🔒 FILTER UTAMA: hanya LM Certicard
        if "(certicard)" not in pecahan.lower():
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

    # =================================================
    # 3. Dedup & sort
    # =================================================
    df = (
        df.sort_values("sell_idr", ascending=True)
          .drop_duplicates(subset="weight_g", keep="first")
          .sort_values("weight_g")
          .reset_index(drop=True)
    )

    label = "Agung Jewellery (LM Certicard)"

    return df, label
