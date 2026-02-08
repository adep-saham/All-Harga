import pandas as pd
import re
from typing import Tuple

# =====================================================
# SOURCE
# =====================================================
URL_HAKABEGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRNGDnYTm5AU122rdZqSxNyn4seEQ9S0wVSdMTzo9QD6MDCITnasamftQLY0tLQ5A"
    "/pub?gid=2039839912&single=true&output=csv"
)

# Buyback resmi (Rp / gram)
BUYBACK_PER_GR = 2649920


# =====================================================
# HELPERS
# =====================================================
def _clean_rp(x) -> int:
    """
    Bersihkan format Rupiah:
    'Rp1,472,360' -> 1472360
    """
    if pd.isna(x):
        return 0
    s = re.sub(r"[^\d]", "", str(x))
    return int(s) if s else 0


# =====================================================
# MAIN PARSER
# =====================================================
def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # -------------------------------------------------
    # 1. Baca CSV TANPA header
    # -------------------------------------------------
    raw = pd.read_csv(URL_HAKABEGOLD, header=None)

    # -------------------------------------------------
    # 2. Ambil hanya baris DATA
    #    (kolom 0 = berat numerik)
    # -------------------------------------------------
    data = raw[pd.to_numeric(raw[0], errors="coerce").notna()].copy()
    if data.empty:
        raise ValueError("Data berat emas tidak ditemukan.")

    # -------------------------------------------------
    # 3. Mapping dasar (SESUAI EXCEL KIRI)
    #    Col 0 = Berat
    #    Col 1 = Harga End User TOTAL (PRESISI)
    # -------------------------------------------------
    df = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": data[0].astype(float),
        "sell_idr": data[1].apply(_clean_rp),  # Harga End User TOTAL (presisi)
        "stock": "Ready"
    })

    # -------------------------------------------------
    # 4. DEDUP FINAL
    #    Jika ada 2 harga per berat:
    #    -> ambil HARGA TERKECIL (harga presisi, bukan pembulatan)
    # -------------------------------------------------
    df = (
        df.sort_values("sell_idr", ascending=True)
          .drop_duplicates(subset="weight_g", keep="first")
    )

    # -------------------------------------------------
    # 5. Hitung Buyback = berat × buyback/gr
    # -------------------------------------------------
    df["buyback_idr"] = df["weight_g"] * BUYBACK_PER_GR

    # -------------------------------------------------
    # 6. Final clean & sort
    # -------------------------------------------------
    df = df[(df["weight_g"] > 0) & (df["sell_idr"] > 0)]
    df = df.sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia (Harga Presisi, No Duplicate)"

    return df, label
