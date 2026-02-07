# scrapers/hakabegold.py
from __future__ import annotations
import re
import pandas as pd
import requests
from io import BytesIO
from typing import Tuple

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

def _clean_numeric(val, is_weight=False):
    """Sangat teliti membersihkan angka dari format Excel yang berantakan."""
    if pd.isna(val) or val == "": return 0.0 if is_weight else 0
    s = str(val).lower().replace("gr", "").strip()
    if is_weight:
        # Menangani koma (0,5 -> 0.5)
        s = s.replace(",", ".")
        try: return float(re.findall(r"[-+]?\d*\.\d+|\d+", s)[0])
        except: return 0.0
    else:
        # Menangani harga (Rp 1.000.000 -> 1000000)
        s = s.split(",")[0] # Buang desimal di belakang koma
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    # 1. IDENTITAS FILE (Sangat Akurat dari htlm.txt)
    # Kita gunakan direct API link yang paling kuat
    resid = "7181A7DF3EAB3581!106"
    authkey = "!AI3AF18"
    direct_url = f"https://onedrive.live.com/download?resid={resid}&authkey={authkey}"
    
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    })

    try:
        # Download dengan verifikasi konten
        r = s.get(direct_url, timeout=30, allow_redirects=True)
        if not r.content.startswith(b'PK'):
            # Jika diblokir, coba trik spoofing referer
            r = s.get(direct_url, headers={"Referer": "https://onedrive.live.com/"}, timeout=30)
        
        if not r.content.startswith(b'PK'):
            return pd.DataFrame(), "HK Logam Mulia — OneDrive memblokir akses (Security Challenge)"

        # 2. PROSES EXCEL (Engine Openpyxl lebih teliti membaca format)
        xls_data = BytesIO(r.content)
        all_sheets = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Sistem Gagal: {str(e)}"

    final_df = pd.DataFrame()
    asof_label = "HK Logam Mulia"
    buyback_val = 0

    # 3. SCANNING SETIAP CELL (Mencari koordinat tabel secara presisi)
    for name, df in all_sheets.items():
        # Cari baris yang mengandung 'Berat' dan 'Harga'
        for row_idx in range(min(len(df), 50)):
            row_data = df.iloc[row_idx].astype(str).str.lower().tolist()
            row_text = " ".join(row_data)
            
            if "berat" in row_text and "end user" in row_text:
                # Mapping kolom berdasarkan index agar tidak tertukar
                col_weight_idx = -1
                col_sell_idx = -1
                
                for col_idx, cell_val in enumerate(row_data):
                    if "berat" in cell_val: col_weight_idx = col_idx
                    if "end user" in cell_val: col_sell_idx = col_idx
                
                if col_weight_idx != -1 and col_sell_idx != -1:
                    # Ambil data di bawah header
                    data_rows = []
                    for next_i in range(row_idx + 1, len(df)):
                        w_raw = df.iloc[next_i, col_weight_idx]
                        p_raw = df.iloc[next_i, col_sell_idx]
                        
                        w = _clean_numeric(w_raw, is_weight=True)
                        p = _clean_numeric(p_raw, is_weight=False)
                        
                        if w > 0 and p > 1000:
                            data_rows.append({
                                "vendor": "HK Logam Mulia",
                                "weight_g": w,
                                "sell_idr": p
                            })
                    
                    if data_rows:
                        final_df = pd.DataFrame(data_rows)
                        
                        # --- EKSTRAK META DATA DARI SELURUH SHEET ---
                        sheet_text = " ".join(df.astype(str).values.flatten()).lower()
                        
                        # Cari Buyback (Logika: cari angka setelah kata buyback)
                        bb_match = re.search(r"buyback.*?(\d[\d\.,]*)", sheet_text)
                        if bb_match:
                            buyback_val = _clean_numeric(bb_match.group(1))
                            asof_label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                        
                        # Cari Tanggal
                        date_match = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", sheet_text)
                        if date_match:
                            asof_label += f" — {date_match.group(1).title()}"
                        
                        break
        if not final_df.empty: break

    if final_df.empty:
        return pd.DataFrame(), "HK Logam Mulia — Data tabel Excel kosong atau format berubah"

    # 4. HITUNG BUYBACK TOTAL
    final_df["buyback_idr"] = (final_df["weight_g"] * buyback_val).astype(int)
    
    return final_df.sort_values("weight_g").reset_index(drop=True), asof_label
