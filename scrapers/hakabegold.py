import pandas as pd
import re
from typing import Tuple

URL_HAKABEGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRNGDnYTm5AU122rdZqSxNyn4seEQ9S0wVSdMTzo9QD6MDCITnasamftQLY0tLQ5A"
    "/pub?gid=2039839912&single=true&output=csv"
)

BUYBACK_PER_GR = 2649920  # FIX: sesuai Excel (Rp2.649.920 / gr)


def _clean_rp(x):
    """ 'Rp1,472,360' -> 1472360 """
    if pd.isna(x):
        return 0
    return int(re.sub(r"[^\d]", "", str(x)) or 0)


def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # =====================================================
    # 1. Baca CSV tanpa header
    # =====================================================
    raw = pd.read_csv(URL_HAKABEGOLD, header=None)

    # =====================================================
    # 2. Ambil hanya baris DATA
    #    (kolom 0 = berat numerik)
    # =====================================================
    data = raw[pd.to_numeric(raw[0], errors="coerce").notna()].copy()

    if data.empty:
        raise ValueError("Data berat emas tidak ditemukan.")

    # =====================================================
    # 3. Mapping FINAL (SESUAI EXCEL KIRI)
    # =====================================================
    df = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": data[0].astype(float),
        # ⬇️ INI KUNCI UTAMA
        "sell_idr": data[1].apply(_clean_rp),  # Harga End User TOTAL
        "buyback_idr": data[0].astype(float) * BUYBACK_PER_GR,
        "stock": "Ready"
    })

    # =====================================================
    # 4. Final cleaning
    # =====================================================
    df = df[(df["weight_g"] > 0) & (df["sell_idr"] > 0)]
    df = df.sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia (Harga End User TOTAL, Buyback x Berat)"

    return df, label
