# scrapers/hakabegold.py
from __future__ import annotations

import re
import base64
import pandas as pd
import requests
from io import BytesIO
from typing import Tuple, Optional
from urllib.parse import urlparse

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

def _create_direct_link(onedrive_url: str) -> str:
    """
    Teknik tingkat tinggi: Mengubah link sharing menjadi link download 1:1
    menggunakan skema encoding resmi Microsoft Graph.
    """
    try:
        # 1. Bersihkan link
        clean_url = onedrive_url.split('?')[0] # Ambil base URL
        # 2. Base64 Encode URL-nya
        base64_bytes = base64.b64encode(clean_url.encode("utf-8"))
        base64_string = base64_bytes.decode("utf-8").replace('=', '').replace('/', '_').replace('+', '-')
        # 3. Masukkan ke skema api v1.0 shares
        return f"https://api.onedrive.com/v1.0/shares/u!{base64_string}/root/content"
    except:
        # Fallback manual jika encoding gagal (menggunakan ID dari htlm.txt Anda)
        return "https://onedrive.live.com/download?resid=7181A7DF3EAB3581!106&authkey=!AI3AF18"

def _clean_price(val) -> int:
    if pd.isna(val) or val == "": return 0
    res = re.sub(r"[^\d]", "", str(val).split(',')[0])
    return int(res) if res else 0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36"
    })

    # 1. Cari URL Iframe
    if not html:
        try:
            r = s.get(URL_HAKABEGOLD, timeout=15)
            html = r.text
        except:
            return pd.DataFrame(), "HK Logam Mulia — Gagal koneksi ke website"

    iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if not iframe_match:
        # Jika website utama berubah, kita pakai link cadangan dari file Anda
        share_url = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8"
    else:
        share_url = iframe_match.group(1).replace("&amp;", "&")

    # 2. Transformasi Link ke Direct Download (Metode API Shares)
    direct_download_url = _create_direct_link(share_url)

    # 3. Download dan Parse Excel
    try:
        resp = s.get(direct_download_url, timeout=30)
        # Jika masih kena HTML, berarti Microsoft butuh authkey
        if "text/html" in resp.headers.get("Content-Type", ""):
             # Fallback ke download standar dengan resid manual
             resp = s.get("https://onedrive.live.com/download?resid=7181A7DF3EAB3581!106&authkey=!AI3AF18", timeout=30)
        
        xls_content = BytesIO(resp.content)
        all_sheets = pd.read_excel(xls_content, sheet_name=None, header=None)
    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Gagal download: {str(e)}"

    # 4. Cari Tabel Harga
    final_df = pd.DataFrame()
    label = "HK Logam Mulia"
    buyback_val = 0

    for _, df in all_sheets.items():
        # Cari baris yang mengandung 'Berat' dan 'End User'
        mask = df.apply(lambda r: r.astype(str).str.contains('Berat', case=False).any() and 
                                 r.astype(str).str.contains('End User', case=False).any(), axis=1)
        if mask.any():
            idx = mask.idxmax()
            df.columns = df.iloc[idx].astype(str).str.lower().str.strip()
            table = df.iloc[idx+1:].copy()
            
            # Cari kolom yang tepat
            c_weight = next((c for c in table.columns if 'berat' in c), None)
            c_price = next((c for c in table.columns if 'end user' in c), None)
            
            if c_weight and c_price:
                table['weight_g'] = pd.to_numeric(table[c_weight], errors='coerce')
                table['sell_idr'] = table[c_price].apply(_clean_price)
                table = table[table['weight_g'] > 0].dropna(subset=['sell_idr'])
                
                # Meta info (Buyback & Tanggal)
                raw_text = df.astype(str).values.flatten()
                text_blob = " ".join(raw_text).lower()
                
                # Cari buyback
                bb_match = re.search(r"buyback.*?(\d[\d\.,]+)", text_blob)
                if bb_match:
                    buyback_val = _clean_price(bb_match.group(1))
                    label += f" — Buyback/g: Rp{buyback_val:,}".replace(",", ".")

                # Cari tanggal
                date_match = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", text_blob)
                if date_match:
                    label += f" — {date_match.group(1).title()}"

                table['vendor'] = "HK Logam Mulia"
                table['buyback_idr'] = (table['weight_g'] * buyback_val).astype(int)
                final_df = table[['vendor', 'weight_g', 'sell_idr', 'buyback_idr']]
                break

    return final_df.sort_values('weight_g'), label
