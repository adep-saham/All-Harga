import pandas as pd
import re
import time
from typing import Tuple

# =====================================================
# SOURCE
# =====================================================
# Pastikan nama variabel ini sesuai dengan yang di-import di app.py
URL_HAKABEGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRNGDnYTm5AU122rdZqSxNyn4seEQ9S0wVSdMTzo9QD6MDCITnasamftQLY0tLQ5A"
    "/pub?gid=2039839912&single=true&output=csv"
)

# =====================================================
# HELPERS
# =====================================================
def _clean_rp(x) -> int:
    """
    Bersihkan format Rupiah dari string menjadi angka murni.
    """
    if pd.isna(x):
        return 0
    s = re.sub(r"[^\d]", "", str(x))
    return int(s) if s else 0

# =====================================================
# MAIN PARSER
# =====================================================
def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    """
    Menarik data dari Google Sheets dan mengambil harga beli (buyback) 
    langsung dari kolom di sheet.
    """
    # Menambahkan cache buster (&cb=...) agar Google memberikan data terbaru
    current_url = f"{URL_HAKABEGOLD}&cb={int(time.time())}"
    
    try:
        # 1. Baca CSV dari URL
        raw = pd.read_csv(current_url, header=None)

        # 2. Filter baris yang berisi data berat (kolom 0 harus numerik)
        data = raw[pd.to_numeric(raw[0], errors="coerce").notna()].copy()
        
        if data.empty:
            return pd.DataFrame(), "Data tidak ditemukan (Sheet Kosong)"

        # 3. Mapping data langsung dari kolom Sheet:
        # Col 0 = Berat (weight_g)
        # Col 1 = Harga Jual (sell_idr)
        # Col 2 = Harga Beli/Buyback (buyback_idr)
        df = pd.DataFrame({
            "vendor": "HK Logam Mulia",
            "weight_g": data[0].astype(float),
            "sell_idr": data[1].apply(_clean_rp),
            "buyback_idr": data[2].apply(_clean_rp), # Ambil harga beli dari kolom C
            "stock": "Ready"
        })

        # 4. Hapus duplikat dan ambil harga terbaik
        df = (
            df.sort_values("sell_idr", ascending=True)
              .drop_duplicates(subset="weight_g", keep="first")
        )

        # 5. Pembersihan akhir dan pengurutan
        df = df[(df["weight_g"] > 0) & (df["sell_idr"] > 0)]
        df = df.sort_values("weight_g").reset_index(drop=True)

        label = f"HK Logam Mulia (Live Sheet Update: {time.strftime('%H:%M:%S')})"

        return df, label

    except Exception as e:
        return pd.DataFrame(), f"Error Hakabe: {str(e)}"
