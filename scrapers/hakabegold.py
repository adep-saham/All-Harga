import pandas as pd
import re
from typing import Tuple

URL_HAKABEGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRNGDnYTm5AU122rdZqSxNyn4seEQ9S0wVSdMTzo9QD6MDCITnasamftQLY0tLQ5A"
    "/pub?gid=2039839912&single=true&output=csv"
)

BUYBACK_PER_GR = 2704000


def _clean_rp(x):
    """
    Bersihkan string Rupiah -> int
    contoh: "Rp2,946,000" -> 2946000
    """
    if pd.isna(x):
        return 0
    s = str(x)
    s = re.sub(r"[^\d]", "", s)
    return int(s) if s else 0


def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # =====================================================
    # 1. Baca CSV TANPA HEADER
    # =====================================================
    raw = pd.read_csv(URL_HAKABEGOLD, header=None)

    # =====================================================
    # 2. Ambil DATA SAJA
    #    Dari struktur sheet kamu:
    #    Row Excel ke-4 s.d ke-20 ≈ index 3 s.d 19
    # =====================================================
    data = raw.iloc[3:20].copy()

    # =====================================================
    # 3. Mapping kolom BERDASARKAN POSISI
    #    Col 0 : Berat (gr)
    #    Col 1 : Harga End User
    #    Col 2 : Harga + PPH 22
    #    Col 3 : Harga + PPH 22 / gr
    #    Col 4 : Stok
    # =====================================================
    df = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": data[0].astype(float),
        "sell_idr": data[3].apply(_clean_rp),
        "buyback_idr": data[0].astype(float).astype(int) * BUYBACK_PER_GR,
        "stock": data[4].astype(str)
    })

    # =====================================================
    # 4. Cleaning akhir
    # =====================================================
    df = df[(df["weight_g"] > 0) & (df["sell_idr"] > 0)]
    df = df.sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia (Google Sheets)"

    return df, label
