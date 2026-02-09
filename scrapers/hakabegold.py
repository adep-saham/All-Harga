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
    # Menghapus semua karakter non-digit kecuali jika ada angka
    s = re.sub(r"[^\d]", "", str(x))
    return int(s) if s else 0

# =====================================================
# MAIN PARSER
# =====================================================
def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    # Menambahkan cache buster untuk data realtime
    current_url = f"{URL_HAKABEGOLD}&cb={int(time.time())}"
    
    try:
        # 1. Baca seluruh CSV mentah
        raw = pd.read_csv(current_url, header=None)

        # -------------------------------------------------
        # 2. LOGIKA MENCARI TANGGAL UPDATE
        # -------------------------------------------------
        date_keywords = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday', '2025', '2026']
        date_row_mask = raw[0].astype(str).str.contains('|'.join(date_keywords), na=False, case=False)
        
        if date_row_mask.any():
            extracted_date = raw[0][date_row_mask].iloc[0].strip()
        else:
            extracted_date = f"Live: {time.strftime('%H:%M:%S')}"

        # -------------------------------------------------
        # 3. LOGIKA MENCARI HARGA BUYBACK PER GRAM (GLOBAL)
        # -------------------------------------------------
        # Mencari baris yang mengandung teks "Buyback Emas Batangan"
        bb_mask = raw.astype(str).apply(lambda x: x.str.contains('Buyback Emas Batangan', case=False, na=False)).any(axis=1)
        global_buyback_rate = 0
        
        if bb_mask.any():
            # Mengambil baris tersebut dan mencari nilai numerik di kolom-kolomnya
            bb_row = raw[bb_mask].iloc[0]
            for val in bb_row:
                cleaned = _clean_rp(val)
                # Harga emas per gram biasanya di kisaran jutaan (e.g., > 2.000.000)
                if cleaned > 1000000:
                    global_buyback_rate = cleaned
                    break
        
        # -------------------------------------------------
        # 4. AMBIL DATA BERAT & HARGA JUAL
        # -------------------------------------------------
        # Ambil baris yang kolom pertamanya numerik (berat emas)
        data = raw[pd.to_numeric(raw[0], errors="coerce").notna()].copy()
        
        if data.empty:
            return pd.DataFrame(), f"Data berat tidak ditemukan ({extracted_date})"

        # Buat DataFrame baru
        df = pd.DataFrame()
        df["vendor"] = "HK Logam Mulia"
        df["weight_g"] = data[0].astype(float)
        
        # Harga Jual diambil dari kolom indeks 1 (Total Harga Jual)
        df["sell_idr"] = data[1].apply(_clean_rp)
        
        # Harga Buyback dihitung: Berat x Harga Buyback per gram
        if global_buyback_rate > 0:
            df["buyback_idr"] = (df["weight_g"] * global_buyback_rate).astype(int)
        else:
            # Fallback jika rate tidak ditemukan (menggunakan kolom 2 x berat)
            df["buyback_idr"] = (df["weight_g"] * data[2].apply(_clean_rp)).astype(int)

        df["stock"] = "Ready"

        # 5. DEDUP & SORT
        df = (
            df.sort_values("sell_idr", ascending=True)
              .drop_duplicates(subset="weight_g", keep="first")
        )
        # Filter hanya data yang valid
        df = df[(df["weight_g"] > 0) & (df["sell_idr"] > 0)]
        df = df.sort_values("weight_g").reset_index(drop=True)

        return df, extracted_date

    except Exception as e:
        return pd.DataFrame(), f"Error HK: {str(e)}"
