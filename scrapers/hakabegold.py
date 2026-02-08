import pandas as pd
import re
import io
from typing import Tuple
from datetime import datetime

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
def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    """
    Parser untuk HK Logam Mulia (Hakabe Gold).
    Ditambahkan parameter 'html' agar sesuai dengan panggilan di app.py.
    """
    try:
        # -------------------------------------------------
        # 1. Baca data
        # Jika 'html' dikirim dari app.py, gunakan io.StringIO
        # Jika tidak, fetch langsung menggunakan URL
        # -------------------------------------------------
        if html and not html.startswith("ERROR"):
            raw = pd.read_csv(io.StringIO(html), header=None)
        else:
            raw = pd.read_csv(URL_HAKABEGOLD, header=None)

        # -------------------------------------------------
        # 2. Ambil hanya baris DATA
        # -------------------------------------------------
        data = raw[pd.to_numeric(raw[0], errors="coerce").notna()].copy()
        if data.empty:
            return pd.DataFrame(), "Gagal: Data berat emas tidak ditemukan."

        # -------------------------------------------------
        # 3. Mapping dasar
        # -------------------------------------------------
        df = pd.DataFrame({
            "vendor": "HK Logam Mulia",
            "weight_g": data[0].astype(float),
            "sell_idr": data[1].apply(_clean_rp),
            "stock": "Ready"
        })

        # -------------------------------------------------
        # 4. Dedup & Sort
        # -------------------------------------------------
        df = (
            df.sort_values("sell_idr", ascending=True)
              .drop_duplicates(subset="weight_g", keep="first")
              .sort_values("weight_g")
        )

        # -------------------------------------------------
        # 5. Hitung Buyback
        # -------------------------------------------------
        df["buyback_idr"] = df["weight_g"] * BUYBACK_PER_GR

        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"Hakabe Gold - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Error Hakabe: {str(e)}"
