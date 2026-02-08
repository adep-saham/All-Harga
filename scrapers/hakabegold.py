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

# Buyback per gram (sesuai sheet kamu)
BUYBACK_PER_GR = 2704000


# =========================================================
# PARSER
# =========================================================
def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # 1. Ambil CSV
    df = pd.read_csv(URL_HAKABEGOLD)

    # 2. Normalisasi nama kolom (ANTI ERROR)
    df.columns = (
        df.columns
        .astype(str)
        .str.lower()
        .str.strip()
        .str.replace("\n", " ")
        .str.replace("  ", " ")
    )

    # 3. Helper cari kolom otomatis
    def find_col(keywords):
        for col in df.columns:
            for kw in keywords:
                if kw in col:
                    return col
        raise KeyError(
            f"Kolom dengan kata kunci {keywords} tidak ditemukan. "
            f"Kolom tersedia: {df.columns.tolist()}"
        )

    # 4. Auto-detect kolom (BERDASARKAN SHEET KAMU)
    col_weight = find_col(["end user", "berat", "gram"])
    col_price  = find_col(["harga", "pph", "jual"])
    col_stock  = find_col(["stok", "stock", "ready"])

    # 5. Mapping data
    df["vendor"] = "HK Logam Mulia"
    df["weight_g"] = pd.to_numeric(df[col_weight], errors="coerce").fillna(0)
    df["sell_idr"] = pd.to_numeric(df[col_price], errors="coerce").fillna(0)
    df["buyback_idr"] = (df["weight_g"] * BUYBACK_PER_GR).astype(int)
    df["stock"] = df[col_stock].astype(str)

    # 6. Filter data valid saja
    final_df = df[
        (df["weight_g"] > 0) & (df["sell_idr"] > 0)
    ][
        ["vendor", "weight_g", "sell_idr", "buyback_idr", "stock"]
    ].copy()

    final_df = final_df.sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia (Google Sheets)"

    return final_df, label
