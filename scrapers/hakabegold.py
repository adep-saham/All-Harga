import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# =========================================================
# CONFIG: URL DARI TOMBOL DOWNLOAD (REPLIKASI)
# =========================================================
# Kita ambil Link Panjang Anda, lalu ganti '/edit' jadi '/download'.
# Parameter 'redeem' adalah kuncinya, jangan dihapus.
LONG_URL = "https://onedrive.live.com/edit?cid=f82ea6cd27a31b67&id=F82EA6CD27A31B67!106&resid=F82EA6CD27A31B67!106&ithint=file%2Cxlsx&embed=1&em=2&wdAllowInteractivity=False&ActiveCell=%27Sheet2%27!A1&Item=%27Sheet2%27!A1%3AF18&wdHideGridlines=True&wdDownloadButton=True&wdInConfigurator=True%2CTrue&migratedtospo=true&redeem=aHR0cHM6Ly8xZHJ2Lm1zL3gvYy9mODJlYTZjZDI3YTMxYjY3L1VRUm5HNk1uemFZdUlJRDRhZ0FBQUFBQUFKbXltZEpuU3l3S211dz9lbT0yJndkQWxsb3dJbnRlcmFjdGl2aXR5PUZhbHNlJkFjdGl2ZUNlbGw9J1NoZWV0MichQTEmSXRlbT0nU2hlZXQyJyFBMTpGMTgmd2RIaWRlR3JpZGxpbmVzPVRydWUmd2REb3dubG9hZEJ1dHRvbj1UcnVlJndkSW5Db25maWd1cmF0b3I9VHJ1ZSZ3ZEluQ29uZmlndXJhdG9yPVRydWU&wdo=2"

# Trik: Ubah mode EDIT jadi DOWNLOAD
URL_HAKABEGOLD = LONG_URL.replace("/edit", "/download")

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # Gunakan Session agar koneksi lebih stabil layaknya browser
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # 1. Download File
        # Kita hit URL yang sudah dimodifikasi jadi /download
        response = session.get(URL_HAKABEGOLD, headers=headers, timeout=60, allow_redirects=True)
        
        if response.status_code != 200:
            return pd.DataFrame(), f"HK Logam Mulia — Gagal Akses (Code: {response.status_code})"

        # Cek apakah malah dapat halaman Login/HTML
        if "text/html" in response.headers.get("Content-Type", "").lower():
            # Fallback: Kadang butuh 'authkey' eksplisit jika 'redeem' gagal direct
            # Kita coba ekstrak token dari link asli jika cara pertama gagal
            return pd.DataFrame(), "HK Logam Mulia — Link Download kedaluwarsa atau butuh login ulang."

        # 2. Proses Excel
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet (Data Anda ada di Sheet2 menurut linknya, tapi kita scan semua biar aman)
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "HK Logam Mulia — File rusak atau format bukan Excel."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # 3. Scanning Data
        for sheet_name, df in xls.items():
            # Scan 50 baris pertama
            for i, row in df.head(50).iterrows():
                row_text = " ".join(row.astype(str).lower())
                
                # KATA KUNCI: "berat" dan "end user"
                if "berat" in row_text and "end user" in row_text:
                    
                    df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                    data = df.iloc[i+1:].copy()
                    
                    c_berat = next((c for c in df.columns if "berat" in c), None)
                    c_jual = next((c for c in df.columns if "end user" in c), None)
                    c_stok = next((c for c in df.columns if "stock" in c or "stok" in c), None)
                    
                    if c_berat and c_jual:
                        # Cleaning Data
                        data["weight_g"] = data[c_berat].apply(lambda x: _clean_number(x, is_float=True))
                        data["sell_idr"] = data[c_jual].apply(lambda x: _clean_number(x, is_float=False))
                        
                        if c_stok:
                            data["stock"] = data[c_stok].fillna("Ready")
                        else:
                            data["stock"] = "Ready"
                        
                        valid = data[(data["weight_g"] > 0) & (data["sell_idr"] > 0)].copy()
                        
                        if not valid.empty:
                            full_text = " ".join(df.astype(str).values.flatten()).lower()
                            
                            dt = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", full_text)
                            if dt: label += f" — {dt.group(1).title()}"
                            
                            bb = re.search(r"buyback.*?(\d[\d\.,]+)", full_text)
                            if bb:
                                buyback_val = _clean_number(bb.group(1))
                                label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                            
                            valid["vendor"] = "HK Logam Mulia"
                            valid["buyback_idr"] = (valid["weight_g"] * buyback_val).astype(int)
                            final_df = valid[["vendor", "weight_g", "sell_idr", "buyback_idr", "stock"]]
                            break
            if not final_df.empty: break

        if final_df.empty:
            return pd.DataFrame(), "HK Logam Mulia — Data tidak ditemukan (Struktur berubah)."

        return final_df.sort_values("weight_g").reset_index(drop=True), label

    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Error: {str(e)}"

def _clean_number(val, is_float=False):
    if pd.isna(val) or val == "": return 0
    s = str(val).lower().replace("gr", "").replace("gram", "").strip()
    try:
        if is_float:
            s = s.replace(",", ".")
            matches = re.findall(r"[-+]?\d*\.\d+|\d+", s)
            return float(matches[0]) if matches else 0
        else:
            s = s.split(",")[0].split(".")[0]
            cleaned = re.sub(r"[^\d]", "", s)
            return int(cleaned) if cleaned else 0
    except:
        return 0
