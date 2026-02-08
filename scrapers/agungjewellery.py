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
    text = text.lower().replace(",", ".")
    m = re.search(r"([\d\.]+)\s*gr", text)
    return float(m.group(1)) if m else 0.0


# =========================
# PARSER
# =========================
def parse_agungjewellery() -> Tuple[pd.DataFrame, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    resp = requests.get(URL_AGUNG, headers=headers, timeout=30)
    resp.raise_for_status()

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    records = []

    # =====================================================
    # 1️⃣ PRIMARY: DOM TABLE PARSING
    # =====================================================
    table = soup.find("table", id="table_17973856")
    if table and table.find("tbody"):
        for row in table.find("tbody").find_all("tr"):
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cols) != 3:
                continue

            pecahan, jual, buy = cols

            if "(certicard)" not in pecahan.lower():
                continue
            if "non rm" in pecahan.lower():
                continue

            weight = _extract_weight(pecahan)
            sell = _clean_rp(jual)
            buyback = _clean_rp(buy)

            if weight > 0 and sell > 0 and buyback > 0:
                records.append({
                    "vendor": "Agung Jewellery",
                    "weight_g": weight,
                    "sell_idr": sell,
                    "buyback_idr": buyback,
                    "stock": "Ready"
                })

    # =====================================================
    # 2️⃣ FALLBACK: REGEX TEXT PARSING
    # =====================================================
    if not records:
        pattern = re.compile(
            r"(\d+(?:[\.,]\d+)?)\s*gr\s*\(Certicard\).*?"
            r"<td>\s*([\d\.]+)\s*</td>\s*<td>\s*([\d\.]+)\s*</td>",
            re.IGNORECASE | re.DOTALL
        )

        for w, jual, buy in pattern.findall(html):
            weight = float(w.replace(",", "."))
            sell = _clean_rp(jual)
            buyback = _clean_rp(buy)

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

    df = (
        pd.DataFrame(records)
        .drop_duplicates(subset="weight_g")
        .sort_values("weight_g")
        .reset_index(drop=True)
    )

    return df, "Agung Jewellery (LM Certicard)"
