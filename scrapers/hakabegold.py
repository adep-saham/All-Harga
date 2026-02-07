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

def _extract_direct_url(html_content: str) -> Optional[str]:
    """Mencari resid dan authkey dari iframe OneDrive untuk membuat link download langsung."""
    # Mencari pola link OneDrive di dalam iframe (baik 1drv.ms atau onedrive.live.com)
    # Kita fokus mencari resid karena itu kunci utamanya
    match = re.search(r'resid=([A-Z0-9!]+)', html_content, re.I)
    auth_match = re.search(r'authkey=([A-Za-z0-9\-_!]+)', html_content, re.I)
    
    if match:
        resid = match.group(1)
        authkey = auth_match.group(1) if auth_match else ""
        return f"https://onedrive.live.com/download?resid={resid}&authkey={authkey}"
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
    s = _session()
    
    # 1. Jika html kosong, ambil dulu dari web utama
    if not html:
        r_main = s.get(URL_HAKABEGOLD, timeout=30)
        html = r_main.text

    # 2. Ambil link download langsung
    download_url = _extract_direct_url(html)
    if not download_url:
        # Fallback ke link manual jika gagal extract (gunakan link terbaru dari screenshot kamu)
        download_url = "https://onedrive.live.com/download?resid=F82EA6CD27A31B67!106&authkey=!AI3AF18"

    # 3. Unduh file XLSX
    r = s.get(download_url, timeout=30, allow_redirects=True)
    if "text/html" in r.headers.get("Content-Type", "").lower():
        raise RuntimeError("OneDrive mengembalikan HTML, bukan file Excel. Pastikan file di OneDrive diset 'Public'.")

    # 4. Parsing Excel
    xls = pd.ExcelFile(BytesIO(r.content))
    data_df = None
    asof_label = "HK Logam Mulia"
    buyback_val = 0

    # Cari di semua sheet, cari yang ada kolom 'Berat'
    for sheet_name in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        
        header_row = None
        for i, row in raw.head(40).iterrows():
            row_str = " ".join(row.astype(str).lower())
            if "berat" in row_str and "harga end user" in row_str:
                header_row = i
                break
        
        if header_row is not None:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row)
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            col_w = next((c for c in df.columns if "berat" in c), None)
            col_s = next((c for c in df.columns if "harga end user" in c), None)
            
            if col_w and col_s:
                df = df[[col_w, col_s]].dropna().copy()
                df.columns = ["weight_g", "sell_raw"]
                df["weight_g"] = df["weight_g"].apply(_to_float)
                df["sell_idr"] = df["sell_raw"].apply(_to_int)
                data_df = df[df["weight_g"] > 0].copy()
                
                # Ekstrak Meta (Tanggal & Buyback) dari sheet yang sama
                full_text = " ".join(raw.astype(str).fillna("").values.ravel()).lower()
                date_m = re.search(r"(\w+\s+\d{1,2},\s+\d{4})", full_text)
                if date_m: asof_label += f" — {date_m.group(1).title()}"
                
                bb_m = re.search(r"buyback.*?([\d\.,]{5,})", full_text)
                if bb_m:
                    buyback_val = _to_int(bb_m.group(1))
                    asof_label += f" — Buyback/gr: Rp{buyback_val:,}".replace(",", ".")
                break

    if data_df is None:
        return pd.DataFrame(), "HK Logam Mulia — Tabel tidak ditemukan"

    data_df["vendor"] = "HK Logam Mulia"
    data_df["buyback_idr"] = (data_df["weight_g"] * buyback_val).astype(int)
    
    return data_df[["vendor", "weight_g", "sell_idr", "buyback_idr"]], asof_label
