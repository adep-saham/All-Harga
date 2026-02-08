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
    """ 'Rp2,946,000' -> 2946000 """
    if pd.isna(x):
        return 0
    s = re.sub(r"[^\d]", "", str(x))
    return int(s) if s else 0


def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # =====================================================
    # 1. Baca CSV tanpa header
    # =====================================================
    raw = pd.read_csv(URL_HAKABEGOLD, header=None)

    # =====================================================
    # 2. Ambil HANYA baris yang kolom 0 = ANGKA (BERAT)
    #    Ini otomatis:
    #    - buang judul
    #    - buang tanggal
    #    - buang "Buyback Emas Batangan"
    # =====================================================
    data = raw[pd.to_numeric(raw[0], errors="coerce").notna()].copy()

    # =====================================================
    # 3. Batasi sampai 20 baris TERATAS saja (permintaan kamu)
    # =====================================================
    data = data.head(20)

    if data.empty:
        raise ValueError("Tidak ditemukan data berat emas numerik.")

    # =====================================================
    # 4. Mapping kolom BERDASARKAN POSISI
    # =====================================================
    df = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": data[0].astype(float),
        "sell_idr": data[3].apply(_clean_rp),
        "buyback_idr": (data[0].astype(float) * BUYBACK_PER_GR).astype(int),
        "stock": data[4].astype(str)
    })

    # =====================================================
    # 5. Final cleaning
    # =====================================================
    df = df[(df["weight_g"] > 0) & (df["sell_idr"] > 0)]
    df = df.sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia (Google Sheets)"

    return df, label
