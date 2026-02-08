import requests
import pandas as pd
import re
from bs4 import BeautifulSoup
from typing import Tuple

URL_AGUNG = "https://agungjewellery.com/harga-lm-2/"

# Samakan buyback policy (sementara)
BUYBACK_PER_GR = 2649920  # bisa kamu ubah / override nanti


def _clean_rp(text: str) -> int:
    """
    Bersihkan format Rupiah:
    'Rp 1.472.360,-' -> 1472360
    """
    if not text:
        return 0
    return int(re.sub(r"[^\d]", "", text) or 0)


def _clean_weight(text: str) -> float:
    """
    '0,5 gram' -> 0.5
    '1 gram'   -> 1.0
    """
    if not text:
        return 0.0
    text = text.lower().replace("gram", "").replace("gr", "").strip()
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_agungjewellery() -> Tuple[pd.DataFrame, str]:
    # =====================================================
    # 1. Request halaman
    # =====================================================
    resp = requests.get(URL_AGUNG, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # =====================================================
    # 2. Cari tabel harga
    # =====================================================
    table = soup.find("table")
    if not table:
        raise ValueError("Tabel harga tidak ditemukan di Agung Jewellery.")

    rows = table.find_all("tr")

    records = []

    # =====================================================
    # 3. Loop baris tabel
    # =====================================================
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cols) < 2:
            continue

        weight = _clean_weight(cols[0])
        price = _clean_rp(cols[1])

        if weight > 0 and price > 0:
            records.append({
                "vendor": "Agung Jewellery",
                "weight_g": weight,
                "sell_idr": price,
                "buyback_idr": int(weight * BUYBACK_PER_GR),
                "stock": "Ready"
            })

    if not records:
        raise ValueError("Data harga Agung Jewellery kosong setelah parsing.")

    df = pd.DataFrame(records)

    # =====================================================
    # 4. Dedup: 1 berat = 1 baris
    #    Ambil harga TERKECIL (harga presisi)
    # =====================================================
    df = (
        df.sort_values("sell_idr", ascending=True)
          .drop_duplicates(subset="weight_g", keep="first")
    )

    df = df.sort_values("weight_g").reset_index(drop=True)

    label = "Agung Jewellery (LM)"

    return df, label
