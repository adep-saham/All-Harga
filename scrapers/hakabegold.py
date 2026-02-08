import pandas as pd
from typing import Tuple

# =========================================================
# GOOGLE SHEETS CSV (PUBLIK)
# =========================================================
URL_HAKABEGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRNGDnYTm5AU122rdZqSxNyn4seEQ9S0wVSdMTzo9QD6MDCITnasamftQLY0tLQ5A"
    "/pub?gid=2039839912&single=true&output=csv"
)

BUYBACK_PER_GR = 2704000  # sesuai sheet kamu

def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # 1. Ambil CSV
    df = pd.read_csv(URL_HAKABEGOLD)

    # 2. Normalisasi kolom
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace("\n", " ")
    )

    # 3. Mapping kolom sesuai SHEET kamu
    # dari screenshot:
    # - End User/gr
    # - Harga+PPH 22/gr
    # - Stok
    df["vendor"] = "HK Logam Mulia"
    df["weight_g"] = df["end user/gr"]
    df["sell_idr"] = df["harga+pph 22/gr"]
    df["buyback_idr"] = df["weight_g"] * BUYBACK_PER_GR
    df["stock"] = df["stok"]

    # 4. Final output
    final_df = df[
        ["vendor", "weight_g", "sell_idr", "buyback_idr", "stock"]
    ].copy()

    final_df = final_df.sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia (Google Sheets)"

    return final_df, label
