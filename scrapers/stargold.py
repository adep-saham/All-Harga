from __future__ import annotations

from datetime import datetime
from io import StringIO
import pandas as pd

# =========================================================
# STAR GOLD SOURCE: Google Sheets Publish CSV (bukan scrape stargold.id)
# =========================================================
URL_STARGOLD = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSVUOrPaB273nGNBr_7h4ZDKWKd3HvEtmQuN4NXK1MDibiDxmB3J4aH1uE2bhn0IpJju1BgeoBJsfad"
    "/pub?gid=2127782410&single=true&output=csv"
)

# Optional (buat info/debug kalau perlu)
URL_STARGOLD_SITE = "https://stargold.id/price/"


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize columns & types to match app.py expectations."""
    # kolom wajib
    required = {"vendor", "weight_g", "sell_idr", "buyback_idr"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"StarGold CSV: kolom wajib tidak lengkap. Missing={sorted(missing)}")

    df = df.copy()
    df["vendor"] = df["vendor"].astype(str).str.upper().str.strip()
    df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce")
    df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
    df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)

    # buang baris invalid
    df = df[df["weight_g"].notna()]
    df = df[df["weight_g"] > 0]

    # sort rapi
    df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
    return df


def parse_stargold(html: str) -> tuple[pd.DataFrame, str]:
    """
    Kompatibel dengan app.py yang memanggil parse_stargold(html).

    Behavior:
    - Kalau `html` berisi CSV (karena app.py fetch URL_STARGOLD), kita parse dari string itu.
    - Kalau `html` kosong / bukan CSV, kita fallback read langsung dari URL_STARGOLD.
    """
    df: pd.DataFrame

    # 1) coba parse dari html string sebagai CSV (kasus umum: fetch_html(URL_STARGOLD) -> text csv)
    try:
        if isinstance(html, str) and ("vendor" in html.lower()) and ("weight_g" in html.lower()):
            df = pd.read_csv(StringIO(html))
        else:
            raise ValueError("Not a CSV payload")
    except Exception:
        # 2) fallback: read langsung dari URL (lebih robust)
        df = pd.read_csv(URL_STARGOLD)

    df = _clean_df(df)

    # update label
    ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
    update_label = f"StarGold (All Vendors) - Updated: {ts}"

    return df, update_label
