# scrapers/hakabegold.py
# ============================================================
# HK Logam Mulia (HakaBe Gold)
# FIXED: direct XLSX download (no iframe, no JS)
# Compatible with existing app.py (DO NOT CHANGE app.py)
# ============================================================

import requests
import pandas as pd
from io import BytesIO
from datetime import datetime


# ============================================================
# PUBLIC URL (WAJIB DIGANTI)
# ============================================================

URL_HAKABEGOLD = "https://onedrive.live.com/download?resid=XXXXXXXXXXXX"
# ⬆️ GANTI dengan link XLSX OneDrive PUBLIC (direct download)


# ============================================================
# INTERNAL
# ============================================================

def _download_xlsx(url: str) -> bytes:
    if "onedrive.live.com/download" not in url:
        raise RuntimeError(
            "URL_HAKABEGOLD harus direct download OneDrive "
            "(https://onedrive.live.com/download?resid=...)"
        )

    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content


def _parse_xlsx(xlsx_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(BytesIO(xlsx_bytes))

    # normalisasi kolom
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    return df


# ============================================================
# PUBLIC API (DIPAKAI app.py)
# ============================================================

def parse_hakabegold(_unused: str = ""):
    """
    Signature DIJAGA untuk kompatibilitas:
    parse_hakabegold("")

    Returns:
        df (DataFrame)
        update_label (str)
    """

    xlsx_bytes = _download_xlsx(URL_HAKABEGOLD)
    df = _parse_xlsx(xlsx_bytes)

    # pastikan kolom wajib ada (sesuai app.py)
    required = {"vendor", "weight_g", "sell_idr", "buyback_idr"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Kolom wajib tidak ditemukan: {missing}")

    update_label = (
        "HK Logam Mulia "
        f"(update: {datetime.now().strftime('%d %b %Y %H:%M')})"
    )

    return df, update_label
