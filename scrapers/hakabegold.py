# scrapers/hakabegold.py
from __future__ import annotations

import re
import base64
import pandas as pd
import requests
from io import BytesIO
from typing import Tuple, Optional

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

def _get_direct_download_url(share_url: str) -> str:
    """
    Menggunakan teknik Microsoft Graph API untuk mengubah 
    sharing link menjadi direct download link yang stabil.
    """
    try:
        # Hapus parameter query jika ada
        base_url = share_url.split('?')[0]
        # Encode URL ke Base64 sesuai spesifikasi OneDrive API
        base64_bytes = base64.b64encode(base_url.encode("utf-8"))
        base64_str = base64_bytes.decode("utf-8").replace('=', '').replace('/', '_').replace('+', '-')
        return f"https://api.onedrive.com/v1.0/shares/u!{base64_str}/root/content"
    except:
        # Fallback terakhir jika API method gagal
        return "https://onedrive.live.com/download?resid=7181A7DF3EAB3581!106&authkey=!AI3AF18"

def _to_int(val) -> int:
    if pd.isna(val) or val == "": return 0
    # Ambil angka saja, buang Rp, titik, koma, dan desimal .00
    s = str(val).split(',')[0].split('.')[0]
    res = re.sub(r"[^\d]", "", s)
    return int(res) if res else 0

def _to_float(val) -> float:
    if pd.isna(val) or val == "": return 0.0
    # Ubah koma jadi titik untuk float (misal 0,5 jadi 0.5)
    s = str(val).lower().replace("gr", "").replace(",", ".").strip()
    try:
        return float(s)
    except:
        return 0.0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36"
    })

    # 1. Ekstraksi URL dari Iframe
    share_link = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8"
    if not html:
        try:
            r = s.get(URL_HAKABEGOLD, timeout=15)
            html = r.text
        except:
            pass
            
    iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if iframe_match:
        share_link = iframe_match.group(1).replace("&amp;", "&")

    # 2. Dapatkan Direct Link & Download
    download_url = _get_direct_download_url(share_link)
    
    try:
        resp = s.get(download_url, timeout=30)
        # Jika OneDrive minta auth/masih kasih HTML, gunakan fallback manual resid
        if "text/html" in resp.headers.get("Content-Type", "").lower():
            fallback = "https://onedrive.live.com/download?resid=7181A7DF3EAB3581!106&authkey=!AI3AF18"
            resp = s.get(fallback, timeout=30)
            
        xls_file = BytesIO(resp.content)
        # Baca semua sheet tanpa header dulu untuk scanning
        all_sheets = pd.read_excel(xls_file, sheet_name=None, header=None)
    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Gagal Koneksi ({str(e)})"

    # 3. Scanning Data secara Teliti
    final_df = pd.DataFrame()
    asof_label = "HK Logam Mulia"
    buyback_per_gr = 0

    for _, df in all_sheets.items():
        # Cari baris header
        # Kriteria: Harus ada kata 'berat' dan 'end user' dalam satu baris
        for i, row in df.head(40).iterrows():
            row_str = " ".join(row.astype(str).lower())
            if "berat" in row_str and "end user" in row_str:
                # Set baris ini sebagai header
                df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                table = df.iloc[i+1:].copy()
                
                # Identifikasi kolom secara fleksibel
                col_w = next((c for c in table.columns if "berat" in c), None)
                col_p = next((c for c in table.columns if "end user" in c), None)
                
                if col_w and col_p:
                    # Bersihkan data
                    table["weight_g"] = table[col_w].apply(_to_float)
                    table["sell_idr"] = table[col_p].apply(_to_int)
                    
                    # Filter: Hanya ambil yang punya berat dan harga
                    table = table[(table["weight_g"] > 0) & (table["sell_idr"] > 1000)].copy()
                    
                    if not table.empty:
                        # --- Cari Meta Data (Tanggal & Buyback) ---
                        full_txt = " ".join(df.astype(str).values.flatten()).lower()
                        
                        # Cari Buyback (angka setelah kata buyback)
                        bb_match = re.search(r"buyback.*?(\d[\d\.,]*)", full_txt)
                        if bb_match:
                            buyback_per_gr = _to_int(bb_match.group(1))
                            asof_label += f" — Buyback/gr: Rp{buyback_per_gr:,}".replace(",", ".")
                        
                        # Cari Tanggal (dd Month yyyy)
                        dt_match = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", full_txt)
                        if dt_match:
                            asof_label += f" — {dt_match.group(1).title()}"
                        
                        table["vendor"] = "HK Logam Mulia"
                        table["buyback_idr"] = (table["weight_g"] * buyback_per_gr).astype(int)
                        final_df = table[["vendor", "weight_g", "sell_idr", "buyback_idr"]]
                        break
        if not final_df.empty: break

    if final_df.empty:
        return pd.DataFrame(), "HK Logam Mulia — Tabel tidak ditemukan di Excel"

    return final_df.sort_values("weight_g").reset_index(drop=True), asof_label
