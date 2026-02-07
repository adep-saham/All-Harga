# scrapers/hakabegold.py
from __future__ import annotations
import re
import pandas as pd
import requests
from io import BytesIO
from typing import Tuple

# Kita gunakan ID file statis yang didapat dari bedah htlm.txt Anda
# resid ini adalah identitas unik file di server Microsoft
RESID = "7181A7DF3EAB3581!106"
AUTHKEY = "!AI3AF18"

def _clean_val(val, is_weight=False):
    if pd.isna(val) or val == "": return 0.0 if is_weight else 0
    s = str(val).lower().replace("gr", "").strip()
    if is_weight:
        # Ganti koma jadi titik untuk berat (0,5 -> 0.5)
        return float(s.replace(",", ".")) if s else 0.0
    else:
        # Ambil angka saja untuk harga, buang desimal di belakang koma
        s = s.split(",")[0]
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    # METODE EKSTRIM: Langsung tembak API Download Microsoft
    # Ini melewati semua script pelindung di halaman preview
    direct_url = f"https://onedrive.live.com/download?resid={RESID}&authkey={AUTHKEY}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0",
        "Referer": "https://onedrive.live.com/"
    }

    try:
        resp = requests.get(direct_url, headers=headers, timeout=30)
        resp.raise_for_status()
        
        # Validasi: Apakah ini beneran file Excel? (Header PK = Excel/ZIP)
        if not resp.content.startswith(b'PK'):
            return pd.DataFrame(), "HK Logam Mulia — OneDrive memblokir akses otomatis"
            
        xls_data = BytesIO(resp.content)
        # Load dengan engine openpyxl (pastikan openpyxl terinstall)
        all_sheets = pd.read_excel(xls_data, sheet_name=None, header=None)
    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Gagal ambil Excel: {str(e)}"

    final_df = pd.DataFrame()
    label = "HK Logam Mulia"
    buyback_val = 0

    # SCANNING SHEET SECARA AGRESIF
    for _, df in all_sheets.items():
        # Cari baris yang mengandung keyword utama
        # Kita pakai regex supaya lebih fleksibel
        for i, row in df.head(30).iterrows():
            row_str = " ".join(row.astype(str).lower())
            if "berat" in row_str and "end user" in row_str:
                # Temukan indeks kolom
                df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                col_w = next((c for c in df.columns if "berat" in c), None)
                col_p = next((c for c in df.columns if "end user" in c), None)
                
                if col_w and col_p:
                    data = df.iloc[i+1:].copy()
                    data["weight_g"] = data[col_w].apply(lambda x: _clean_val(x, True))
                    data["sell_idr"] = data[col_p].apply(lambda x: _clean_val(x, False))
                    
                    # Filter data yang valid saja
                    data = data[(data["weight_g"] > 0) & (data["sell_idr"] > 1000)].copy()
                    
                    if not data.empty:
                        # EKSTRAK META (Tanggal & Buyback)
                        full_text = " ".join(df.astype(str).values.flatten()).lower()
                        
                        # Cari angka buyback (biasanya di kalimat 'Buyback Rp 1.100.000/gram')
                        bb_match = re.search(r"buyback.*?([\d\.,]{5,})", full_text)
                        if bb_match:
                            buyback_val = _clean_val(bb_match.group(1))
                            label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                        
                        # Cari tanggal
                        date_match = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", full_text)
                        if date_match:
                            label += f" — {date_match.group(1).title()}"

                        data["vendor"] = "HK Logam Mulia"
                        data["buyback_idr"] = (data["weight_g"] * buyback_val).astype(int)
                        final_df = data[["vendor", "weight_g", "sell_idr", "buyback_idr"]]
                        break
        if not final_df.empty: break

    return final_df.sort_values("weight_g").reset_index(drop=True), label
