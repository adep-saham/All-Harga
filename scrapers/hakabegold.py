import pandas as pd
from typing import Tuple

URL_HAKABEGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRNGDnYTm5AU122rdZqSxNyn4seEQ9S0wVSdMTzo9QD6MDCITnasamftQLY0tLQ5A"
    "/pub?gid=2039839912&single=true&output=csv"
)

BUYBACK_PER_GR = 2704000


def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # 1. Baca CSV TANPA HEADER
    df = pd.read_csv(URL_HAKABEGOLD, header=None)

    # 2. Buang baris non-numerik di kolom pertama
    #    (judul besar / tanggal)
    df = df[pd.to_numeric(df[0], errors="coerce").notna()]

    if df.empty:
        raise ValueError("Tidak ada data numerik ditemukan di CSV.")

    # 3. Mapping kolom BERDASARKAN POSISI
    # Asumsi struktur:
    # col 0 = End User/gr
    # col 1 = Harga+PPH 22
    # col 2 = Harga+PPH 22/gr
    # col 3 = Stok

    df = df.reset_index(drop=True)

    df_final = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": df[0].astype(float),
        "sell_idr": df[2].astype(float),
        "buyback_idr": (df[0].astype(float) * BUYBACK_PER_GR).astype(int),
        "stock": df[3].astype(str)
    })

    df_final = df_final.sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia (Google Sheets)"

    return df_final, label
