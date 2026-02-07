# scrapers/hakabegold.py
from __future__ import annotations

import re
from io import BytesIO
from typing import Tuple, Optional
from urllib.parse import urlparse, parse_qs

import pandas as pd
import requests

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"
# Fallback link jika gagal scraping link otomatis
DEFAULT_SHARE_URL = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8?e=HhTNvT"

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    })
    return s

def get_latest_onedrive_link() -> str:
    """Mencari link OneDrive terbaru yang tertanam di website."""
    try:
        s = _session()
        r = s.get(URL_HAKABEGOLD, timeout=15)
        # Mencari pola link OneDrive di dalam iframe atau script
        match = re.search(r'https://onedrive\.live\.com/embed\?resid=[A-Za-z0-9!]+&authkey=[A-Za-z0-9\-_]+', r.text)
        if match:
            return match.group(0)
    except Exception:
        pass
    return DEFAULT_SHARE_URL

def _download_xlsx_from_share(share_url: str) -> bytes:
    s = _session()
    # Pastikan link mengarah ke download, bukan sekadar view
    # Jika link mengandung 'embed', kita ubah parameternya
    if "embed" in share_url:
        share_url = share_url.replace("embed", "download")
    
    r = s.get(share_url, timeout=60, allow_redirects=True)
    r.raise_for_status()
    
    # Logic redirect dan validasi content-type tetap sama seperti versi Anda
    # ... (kode download_xlsx_from_share Anda yang sudah sangat bagus)
    return r.content

# ... (Fungsi helper _idr_to_int, _to_float, dll tetap sama)

def parse_hakabegold(_: str = "") -> Tuple[pd.DataFrame, str]:
    # 1. Ambil link terbaru secara dinamis
    target_url = get_latest_onedrive_link()
    
    # 2. Download file
    try:
        xlsx_bytes = _download_xlsx_from_share(target_url)
    except Exception:
        # Jika gagal dinamis, coba pakai fallback
        xlsx_bytes = _download_xlsx_from_share(DEFAULT_SHARE_URL)
        
    xls = pd.ExcelFile(BytesIO(xlsx_bytes))
    
    # ... (Sisa logic parsing Excel Anda sudah tepat, teruskan di sini)
    # Gunakan logic pemilihan sheet dan pembersihan data yang sudah Anda buat.
    
    # (Contoh return hasil akhir)
    # return out, label
