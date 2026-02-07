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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    })
    return s

def _extract_direct_url(s: requests.Session, main_html: str) -> str:
    """Mengekstrak resid dan authkey dari iframe untuk membuat link download biner."""
    # 1. Cari URL iframe OneDrive dari HTML Blogger
    iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', main_html, re.I)
    if not iframe_match:
        # Fallback link jika iframe tidak ditemukan (berdasarkan data htlm.txt Anda)
        return "https://onedrive.live.com/download?resid=F82EA6CD27A31B67!106&authkey=!AI3AF18"
    
    iframe_url = iframe_match.group(1).replace("&amp;", "&")
    
    # 2. Ikuti redirect untuk mendapatkan resid & authkey dari URL akhir
    try:
        r = s.get(iframe_url, allow_redirects=True, timeout=15)
        final_url = r.url
        qs = parse_qs(urlparse(final_url).query)
        
        resid = (qs.get("resid") or [None])[0]
        authkey = (qs.get("authkey") or [None])[0]
        
        if not resid:
            # Cari resid di dalam body HTML jika tidak ada di URL
            res_m = re.search(r'["\']resid["\']\s*:\s*["\']([^"\']+)["\']', r.text)
            resid = res_m.group(1) if res_m else "F82EA6CD27A31B67!106"
            
        dl_url = f"https://onedrive.live.com/download?resid={resid}"
        if authkey:
            dl_url += f"&authkey={authkey}"
        return dl_url
    except:
        return "https://onedrive.live.com/download?resid=F82EA6CD27A31B67!106&authkey=!AI3AF18"

def _clean_val(val) -> int:
    if pd.isna(val) or val is None: return 0
    return int(re.sub(r"[^\d]", "", str(val))) if re.sub(r"[^\d]", "", str(val)) else 0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    s = _session()
    
    # Ambil HTML utama jika kosong
    if not html:
        r = s.get(URL_HAKABEGOLD, timeout=15)
        html = r.text

    # Dapatkan link download langsung
    download_url = _extract_direct_url(s, html)
    
    # Unduh file Excel
    r_file = s.get(download_url, timeout=30)
    if "text/html" in r_file.headers.get("Content-Type", "").lower():
        raise RuntimeError("Gagal mengunduh file Excel (OneDrive mengembalikan HTML).")

    # Baca semua sheet untuk mencari tabel
    xls = pd.read_excel(BytesIO(r_file.content), sheet_name=None, header=None)
    
    data_df = None
    asof_label = "HK Logam Mulia"
    buyback_val = 0

    for name, df in xls.items():
        # Cari baris yang mengandung teks 'Berat'
        mask = df.apply(lambda row: row.astype(str).str.contains('Berat', case=False).any(), axis=1)
        if mask.any():
            idx = mask.idxmax()
            header = df.iloc[idx].astype(str).str.strip().tolist()
            temp_df = df.iloc[idx+1:].copy()
            temp_df.columns = header
            
            col_w = next((c for c in header if 'Berat' in c), None)
            col_s = next((c for c in header if 'Harga End User' in c), None)
            
            if col_w and col_s:
                temp_df = temp_df[[col_w, col_s]].dropna()
                temp_df.columns = ["weight_g", "sell_raw"]
                temp_df["weight_g"] = pd.to_numeric(temp_df["weight_g"], errors='coerce')
                temp_df["sell_idr"] = temp_df["sell_raw"].apply(_clean_val)
                data_df = temp_df[temp_df["weight_g"] > 0].copy()
                
                # Cari meta data (Tanggal & Buyback)
                all_text = " ".join(df.astype(str).values.flatten()).lower()
                # Ekstrak Tanggal
                date_m = re.search(r"(\w+\s+\d{1,2},\s+\d{4})", all_text)
                if date_m: asof_label += f" — {date_m.group(1).title()}"
                
                # Ekstrak Buyback
                bb_m = re.search(r"buyback.*?([\d\.,]{5,})", all_text)
                if bb_m:
                    buyback_val = _clean_val(bb_m.group(1))
                    asof_label += f" — Buyback/gr: Rp{buyback_val:,}".replace(",", ".")
                break

    if data_df is None:
        return pd.DataFrame(), "HK Logam Mulia — Data tidak ditemukan"

    data_df["vendor"] = "HK Logam Mulia"
    data_df["buyback_idr"] = (data_df["weight_g"] * buyback_val).astype(int)
    
    return data_df[["vendor", "weight_g", "sell_idr", "buyback_idr"]], asof_label
