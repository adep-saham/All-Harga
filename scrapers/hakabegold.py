import pandas as pd
import re
from typing import Tuple

URL_HAKABEGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRNGDnYTm5AU122rdZqSxNyn4seEQ9S0wVSdMTzo9QD6MDCITnasamftQLY0tLQ5A"
    "/pub?gid=2039839912&single=true&output=csv"
)

BUYBACK_PER_GR = 2649920  # Rp2.649.920 / gr


def _clean_rp(x):
    if pd.isna(x):
        return 0
    return int(re.sub(r"[^\d]", "", str(x)) or 0)


def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # 1. Baca CSV
    raw = pd.read_csv(URL_HAKABEGOLD, header=None)

    # 2. Ambil baris dengan berat numerik
    data = raw[pd.to_numeric(raw[0], errors="coerce").notna()].copy()

    # 3. Mapping dasar
    df = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": data[0].astype(float),
        "sell_idr": data[1].apply(_clean_rp),  # Harga End User TOTAL
        "stock": "Ready"
    })

    # 4. 🔒 DEDUP: ambil harga TERBESAR per berat
    df = (
        df.sort_values("sell_idr", ascending=False)
          .drop_duplicates(subset="weight_g", keep="first")
    )

    # 5. Buyback = berat × buyback/gr
    df["buyback_idr"] = df["weight_g"] * BUYBACK_PER_GR

    # 6. Final sort
    df = df.sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia (Final – No Duplicate)"

    return df, label
