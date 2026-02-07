# scrapers/hakabegold.py
# Scraper HK Logam Mulia (Hakabe Gold)
# Strategy:
# 1) Ambil HTML halaman utama logammuliahk.com
# 2) Cari link OneDrive / 1drv / Excel embed secara otomatis
# 3) Download XLSX
# 4) Parse tabel harga emas
#
# Catatan:
# - Hash #work tidak ikut terkirim ke server → cukup base URL
# - Tidak pakai Selenium
# - Tidak hardcode token OneDrive

import io
import re
import requests
import pandas as pd
from typing import Optional, Tuple


# =========================================================
# CONFIG
# =========================================================

URL_HAKABEGOLD = "https://www.logammuliahk.com/"
REQUEST_TIMEOUT = 30


# =========================================================
# SESSION
# =========================================================

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    })
    return s


# =========================================================
# STEP 1 — FETCH HTML
# =========================================================

def _fetch_home_html() -> str:
    s = _session()
    r = s.get(URL_HAKABEGOLD, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text or ""


# =========================================================
# STEP 2 — DISCOVER ONEDRIVE / EXCEL LINK
# =========================================================

def _discover_onedrive_share_url(html: str) -> Optional[str]:
    """
    Cari link OneDrive / 1drv / Excel embed dari HTML.
    """
    if not html:
        return None

    # Normalisasi escape JS
    h = html.replace("\\u0026", "&").replace("\\/", "/")

    patterns = [
        r"(https://1drv\.ms/[^\s\"'<>]+)",
        r"(https://onedrive\.live\.com/[^\s\"'<>]+)",
        r"(https://excel\.officeapps\.live\.com/x/_layouts/xlembed\.aspx\?[^\s\"'<>]+)",
    ]

    for pat in patterns:
        m = re.search(pat, h, flags=re.I)
        if m:
            return m.group(1).rstrip(").,;")

    return None


# =========================================================
# STEP 3 — DOWNLOAD XLSX
# =========================================================

def _download_xlsx(url: str) -> bytes:
    s = _session()
    r = s.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    r.raise_for_status()

    ctype = (r.headers.get("Content-Type") or "").lower()

    # OneDrive sering balikin HTML kalau link tidak public
    if "html" in ctype:
        raise RuntimeError(
            "OneDrive mengembalikan HTML (bukan XLSX). "
            "Link tidak public-downloadable."
        )

    return r.content


# =========================================================
# STEP 4 — PARSE XLSX
# =========================================================

def _idr_to_int(val) -> int:
    if pd.isna(val):
        return 0
    s = re.sub(r"[^\d]", "", str(val))
    return int(s) if s else 0


def _parse_xlsx(xlsx_bytes: bytes) -> pd.DataFrame:
    bio = io.BytesIO(xlsx_bytes)

    # Ambil sheet pertama (biasanya)
    df = pd.read_excel(bio, sheet_name=0)

    # Normalisasi kolom
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Mapping kolom fleksibel
    col_weight = next((c for c in df.columns if "berat" in c), None)
    col_sell = next((c for c in df.columns if "end user" in c and "/gr" not in c), None)
    col_sell_gr = next((c for c in df.columns if "end user/gr" in c), None)

    if not col_weight or not col_sell:
        raise RuntimeError("Struktur kolom XLSX tidak sesuai.")

    out = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": df[col_weight],
        "sell_idr": df[col_sell].apply(_idr_to_int),
        "buyback_idr": 0,  # buyback biasanya terpisah
    })

    out["weight_g"] = pd.to_numeric(out["weight_g"], errors="coerce").fillna(0.0)
    out = out[out["weight_g"] > 0]
    out = out.sort_values("weight_g").reset_index(drop=True)

    return out


# =========================================================
# PUBLIC API (dipanggil dari app.py)
# =========================================================

def parse_hakabegold(_: str = "") -> Tuple[pd.DataFrame, str]:
    """
    Return:
      df columns: vendor, weight_g, sell_idr, buyback_idr
      label: str
    """
    html = _fetch_home_html()
    share_url = _discover_onedrive_share_url(html)

    if not share_url:
        raise RuntimeError("Link OneDrive / Excel tidak ditemukan di HTML website.")

    xlsx_bytes = _download_xlsx(share_url)
    df = _parse_xlsx(xlsx_bytes)

    label = "HK Logam Mulia — sumber XLSX (auto-discovered)"
    return df, label
