# scrapers/hakabegold.py
from __future__ import annotations
import re
import pandas as pd
import requests
from io import BytesIO
from typing import Tuple

# Konfigurasi Akses (Berdasarkan htlm.txt Anda)
RESID = "7181A7DF3EAB3581!106"
AUTHKEY = "!AI3AF18"
URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

def _clean_numeric(val, is_weight=False):
    if pd.isna(val) or val == "": return 0.0 if is_weight else 0
    s = str(val).lower().replace("gr", "").replace("gram", "").strip()
    if is_weight:
        s = s.replace(",", ".")
        try: return float(re.findall(r"[-+]?\d*\.\d+|\d+", s)[0])
        except: return 0.0
    else:
        s = s.split(",")[0].split(".")[0] # Ambil angka utama saja
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    """
    Programmer Handal Sedunia Mode: Stealth Browser Emulation
    """
    s = requests.Session()
    
    # Header yang meniru identitas Browser Chrome Desktop secara sempurna
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    })

    try:
        # STEP 1: Handshake (Pura-pura buka halaman utama OneDrive untuk dapet Session Cookie)
        s.get("https://onedrive.live.com/", timeout=15)
        
        # STEP 2: Download Langsung menggunakan Link API dengan Authkey
        download_url = f"https://onedrive.live.com/download?resid={RESID}&authkey={AUTHKEY}"
        resp = s.get(download_url, timeout=30, allow_redirects=True)
        
        # Validasi: Apakah ini beneran file Excel (PK)?
        if not resp.content.startswith(b'PK'):
             # Jika gagal, coba sekali lagi dengan Referer
             resp = s.get(download_url, headers={"Referer": "https://onedrive.live.com/"}, timeout=30)
             
        if not resp.content.startswith(b'PK'):
            return pd.DataFrame(), "HK Logam Mulia — Diblokir OneDrive (Challenge Active)"

        # STEP 3: Parsing Data Teliti
        xls = pd.read_excel(BytesIO(resp.content), sheet_name=None, header=None, engine='openpyxl')
        
    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Gagal Sistem: {str(e)}"

    final_df = pd.DataFrame()
    asof_label = "HK Logam Mulia"
    buyback_val = 0

    # SCANNING TABLE
    for _, df in xls.items():
        for i, row in df.head(40).iterrows():
            row_str = " ".join(row.astype(str).lower())
            if "berat" in row_str and "end user" in row_str:
                df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                col_w = next((c for c in df.columns if "berat" in c), None)
                col_p = next((c for c in df.columns if "end user" in c), None)
                
                if col_w and col_p:
                    # Ambil semua data di bawah header
                    sub = df.iloc[i+1:].copy()
                    sub["weight_g"] = sub[col_w].apply(lambda x: _clean_numeric(x, True))
                    sub["sell_idr"] = sub[col_p].apply(lambda x: _clean_numeric(x, False))
                    
                    # Buang baris kosong
                    valid_data = sub[(sub["weight_g"] > 0) & (sub["sell_idr"] > 1000)].copy()
                    
                    if not valid_data.empty:
                        # Ekstrak Meta (Tanggal & Buyback) dari sisa teks di sheet
                        sheet_text = " ".join(df.astype(str).values.flatten()).lower()
                        bb_match = re.search(r"buyback.*?([\d\.,]{6,})", sheet_text)
                        if bb_match:
                            buyback_val = _clean_numeric(bb_match.group(1))
                            asof_label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                        
                        dt_match = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", sheet_text)
                        if dt_match:
                            asof_label += f" — {dt_match.group(1).title()}"
                            
                        valid_data["vendor"] = "HK Logam Mulia"
                        valid_data["buyback_idr"] = (valid_data["weight_g"] * buyback_val).astype(int)
                        final_df = valid_data[["vendor", "weight_g", "sell_idr", "buyback_idr"]]
                        break
        if not final_df.empty: break

    return final_df.sort_values("weight_g").reset_index(drop=True), asof_label
