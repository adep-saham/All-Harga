# scrapers/hakabegold.py
from __future__ import annotations

import re
import pandas as pd
import requests
from io import BytesIO
from typing import Tuple, Optional
from urllib.parse import urlparse, parse_qs

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })
    return s

def _extract_download_url(html_content: str) -> Optional[str]:
    """Mengambil resid dan authkey dari iframe OneDrive untuk membuat link download langsung."""
    # Mencari pola link OneDrive di dalam iframe
    match = re.search(r'https://onedrive\.live\.com/embed\?resid=([A-Za-z0-9!]+)(&authkey=([A-Za-z0-9\-_!]+))?', html_content)
    if match:
        resid = match.group(1)
        authkey = match.group(3)
        # Konstruksi link direct download yang melewati halaman preview
        base_url = f"https://onedrive.live.com/download?resid={resid}"
        if authkey:
            base_url += f"&authkey={authkey}"
        return base_url
    return None

def _to_int(x) -> int:
    if x is None or pd.isna(x): return 0
    s = re.sub(r"[^\d]", "", str(x))
    return int(s) if s.isdigit() else 0

def _to_float(x) -> float:
    if x is None or pd.isna(x): return 0.0
    try:
        return float(str(x).replace(",", "."))
    except:
        return 0.0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    """Fungsi utama untuk mengambil dan memproses data dari Hakabe Gold."""
    s = _session()
    
    # 1. Ambil link download langsung dari HTML utama
    download_url = _extract_download_url(html)
    if not download_url:
        raise RuntimeError("Gagal menemukan link spreadsheet OneDrive di halaman website.")

    # 2. Unduh file XLSX
    r = s.get(download_url, timeout=30)
    r.raise_for_status()
    
    # Validasi apakah benar-benar file Excel (bukan HTML)
    if "text/html" in r.headers.get("Content-Type", "").lower():
        raise RuntimeError("OneDrive mengembalikan HTML (Preview). Link sharing mungkin tidak publik atau struktur berubah.")

    # 3. Proses Excel dengan Pandas
    # Membaca semua sheet untuk mencari tabel harga
    xls = pd.ExcelFile(BytesIO(r.content))
    data_df = None
    asof_label = "HK Logam Mulia"
    buyback_val = 0

    for sheet_name in xls.sheet_names:
        # Baca mentah untuk mencari posisi header
        raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        
        # Cari baris yang mengandung "Berat" dan "Harga"
        header_row = None
        for i, row in raw.head(50).iterrows():
            row_str = " ".join(row.astype(str).lower())
            if "berat" in row_str and "harga" in row_str:
                header_row = i
                break
        
        if header_row is not None:
            # Baca ulang dengan header yang benar
            df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row)
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            # Mapping kolom (Berat, Harga End User)
            col_w = next((c for c in df.columns if "berat" in c), None)
            col_s = next((c for c in df.columns if "harga end user" in c), None)
            
            if col_w and col_s:
                df = df[[col_w, col_s]].dropna().copy()
                df.columns = ["weight_g", "sell_raw"]
                df["weight_g"] = df["weight_g"].apply(_to_float)
                df["sell_idr"] = df["sell_raw"].apply(_to_int)
                data_df = df[df["weight_g"] > 0].copy()
                
                # Cari Buyback & Tanggal di sekitar tabel
                all_text = " ".join(raw.astype(str).fillna("").values.ravel()).lower()
                
                # Ekstrak tanggal (pola: February 7, 2026)
                date_match = re.search(r"(\w+\s+\d{1,2},\s+\d{4})", all_text)
                if date_match:
                    asof_label += f" — {date_match.group(1)}"
                
                # Ekstrak buyback (pola: Buyback ... /gram)
                bb_match = re.search(r"buyback.*?([\d\.,]{5,})", all_text)
                if bb_match:
                    buyback_val = _to_int(bb_match.group(1))
                    asof_label += f" — Buyback/gr: Rp{buyback_val:,}".replace(",", ".")
                
                break

    if data_df is None:
        return pd.DataFrame(), "HK Logam Mulia — Tabel tidak ditemukan"

    # 4. Finalisasi DataFrame
    data_df["vendor"] = "HK Logam Mulia"
    data_df["buyback_idr"] = (data_df["weight_g"] * buyback_val).astype(int)
    
    out = data_df[["vendor", "weight_g", "sell_idr", "buyback_idr"]].sort_values("weight_g").reset_index(drop=True)
    return out, asof_label
