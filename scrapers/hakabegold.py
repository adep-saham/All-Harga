import pandas as pd
import re
import time
from typing import Tuple

# =====================================================
# SOURCE
# =====================================================
URL_HAKABEGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRNGDnYTm5AU122rdZqSxNyn4seEQ9S0wVSdMTzo9QD6MDCITnasamftQLY0tLQ5A"
    "/pub?gid=2039839912&single=true&output=csv"
)

# =====================================================
# HELPERS
# =====================================================
def _clean_rp(x) -> int:
    if pd.isna(x):
        return 0
    s = re.sub(r"[^\d]", "", str(x))
    return int(s) if s else 0

# =====================================================
# MAIN PARSER
# =====================================================
def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # Menambahkan cache buster
    current_url = f"{URL_HAKABEGOLD}&cb={int(time.time())}"
    
    try:
        # 1. Baca seluruh CSV mentah
        raw = pd.read_csv(current_url, header=None)

        # -------------------------------------------------
        # 2. LOGIKA MENCARI TANGGAL (UPDATE BARU)
        # -------------------------------------------------
        # Kita cari di kolom pertama (indeks 0) baris yang mengandung nama hari atau tahun
        date_keywords = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday', '2026']
        date_row = raw[0].astype(str).str.contains('|'.join(date_keywords), na=False)
        
        if date_row.any():
            # Ambil teks tanggal pertama yang ditemukan
            extracted_date = raw[0][date_row].iloc[0].strip()
        else:
            extracted_date = f"Live: {time.strftime('%H:%M:%S')}"

        # -------------------------------------------------
        # 3. Ambil data BERAT (Hanya baris numerik)
        # -------------------------------------------------
        data = raw[pd.to_numeric(raw[0], errors="coerce").notna()].copy()
        
        if data.empty:
            return pd.DataFrame(), f"Data berat tidak ditemukan ({extracted_date})"

        # 4. Mapping data
        df = pd.DataFrame({
            "vendor": "HK Logam Mulia",
            "weight_g": data[0].astype(float),
            "sell_idr": data[1].apply(_clean_rp),
            "buyback_idr": data[2].apply(_clean_rp),
            "stock": "Ready"
        })

        # 5. DEDUP & SORT
        df = (
            df.sort_values("sell_idr", ascending=True)
              .drop_duplicates(subset="weight_g", keep="first")
        )
        df = df[(df["weight_g"] > 0) & (df["sell_idr"] > 0)]
        df = df.sort_values("weight_g").reset_index(drop=True)

        # Masukkan tanggal yang ditemukan ke dalam label
        label = f"HK Logam Mulia ({extracted_date})"

        return df, label

    except Exception as e:
        return pd.DataFrame(), f"Error Hakabe: {str(e)}"
