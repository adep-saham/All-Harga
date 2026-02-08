import pandas as pd
import re
from typing import Tuple

URL_HAKABEGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRNGDnYTm5AU122rdZqSxNyn4seEQ9S0wVSdMTzo9QD6MDCITnasamftQLY0tLQ5A"
    "/pub?gid=2039839912&single=true&output=csv"
)


def _clean_rp(x):
    """ 'Rp2,946,000' -> 2946000 """
    if pd.isna(x):
        return 0
    return int(re.sub(r"[^\d]", "", str(x)) or 0)


def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # =====================================================
    # 1. Baca CSV tanpa header
    # =====================================================
    raw = pd.read_csv(URL_HAKABEGOLD, header=None)

    # =====================================================
    # 2. Ambil hanya baris DATA (kolom 0 = Berat numerik)
    # =====================================================
    data = raw[pd.to_numeric(raw[0], errors="coerce").notna()].copy()
    if data.empty:
        raise ValueError("Data berat emas tidak ditemukan.")

    # =====================================================
    # 3. Ambil BUYBACK / GRAM dari baris bawah sheet
    # =====================================================
    buyback_row = raw[
        raw[0].astype(str).str.contains("buyback", case=False, na=False)
    ]
    if buyback_row.empty:
        raise ValueError("Baris Buyback tidak ditemukan di sheet.")

    buyback_per_gr = _clean_rp(buyback_row.iloc[0, 3])

    # =====================================================
    # 4. Mapping SESUAI EXCEL KIRI (CHECKLIST)
    #    Col 0 = Berat
    #    Col 2 = Harga End User / gr
    # =====================================================
    df = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": data[0].astype(float),
        "sell_idr": data[2].apply(_clean_rp),   # Harga End User / gr
        "buyback_idr": data[0].astype(float) * buyback_per_gr,
        "stock": "Ready"
    })

    # =====================================================
    # 5. Final clean & sort
    # =====================================================
    df = df[(df["weight_g"] > 0) & (df["sell_idr"] > 0)]
    df = df.sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia (Harga End User/gr, Buyback x Berat)"

    return df, label
