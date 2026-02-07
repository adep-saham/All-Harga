# scrapers/hakabegold.py
# ============================================================
# HakaBe Gold Scraper
# Direct XLSX Downloader (OneDrive public link)
# No iframe, no JS, server-safe
# ============================================================

import requests
import pandas as pd
from io import BytesIO
from datetime import datetime
from typing import Optional


# ============================================================
# CONFIG
# ============================================================

HAKABEGOLD_XLSX_URL = (
    "https://onedrive.live.com/download?resid=XXXXXXXXXXXX"
)
# ⬆️ GANTI dengan direct-download link XLSX (WAJIB PUBLIC)

REQUEST_TIMEOUT = 30
SOURCE_NAME = "hakabegold"


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _validate_xlsx_url(url: str) -> None:
    if not url:
        raise RuntimeError("XLSX URL kosong")

    if "onedrive.live.com/download" not in url:
        raise RuntimeError(
            "URL bukan direct-download OneDrive. "
            "Gunakan https://onedrive.live.com/download?resid=..."
        )


def _download_xlsx(url: str) -> bytes:
    _validate_xlsx_url(url)

    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as e:
        raise RuntimeError(f"Gagal download XLSX HakaBe Gold: {e}") from e


def _parse_xlsx(xlsx_bytes: bytes) -> pd.DataFrame:
    try:
        df = pd.read_excel(BytesIO(xlsx_bytes))
    except Exception as e:
        raise RuntimeError("Gagal parse XLSX HakaBe Gold") from e

    # Normalisasi nama kolom
    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    return df


# ============================================================
# PUBLIC API
# ============================================================

def fetch_hakabegold(
    xlsx_url: Optional[str] = None
) -> pd.DataFrame:
    """
    Fetch & parse harga emas HakaBe Gold

    Returns:
        pd.DataFrame
    """
    url = xlsx_url or HAKABEGOLD_XLSX_URL

    xlsx_bytes = _download_xlsx(url)
    df = _parse_xlsx(xlsx_bytes)

    # Metadata
    df["_source"] = SOURCE_NAME
    df["_fetched_at"] = datetime.utcnow()

    return df


# ============================================================
# LOCAL DEBUG
# ============================================================

if __name__ == "__main__":
    df = fetch_hakabegold()
    print("✅ HakaBe Gold loaded")
    print(df.head())
    print(f"Total rows: {len(df)}")
