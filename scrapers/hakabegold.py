import pandas as pd
import requests
import base64
import re
from io import BytesIO
from typing import Tuple

# =========================================================
# LINK ONEDRIVE ANDA (SUDAH TERTANAM)
# =========================================================
MY_ONEDRIVE_LINK = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8"

# Dummy variable agar app.py tidak error
URL_HAKABEGOLD = MY_ONEDRIVE_LINK

def create_direct_link(share_url):
    """
    Mengubah Link Share (1drv.ms) menjadi Link API Download Resmi.
    Metode: OneDrive API v1.0 Encoded Shares.
    """
    try:
        # 1. Encode URL ke Base64
        base64_value = base64.b64encode(share_url.encode("utf-8")).decode("utf-8")
        
        # 2. Format sesuai standar API OneDrive (URL-Safe Base64)
        #    - Tambah 'u!' di depan
        #    - Hapus padding '=' di belakang
        #    - Ganti '/' jadi '_' dan '+' jadi '-'
        encoded_url = "u!" + base64_value.rstrip("=").replace("/", "_").replace("+", "-")
        
        # 3. Return URL API
        return f"https://api.onedrive.com/v1.0/shares/{encoded_url}/root/content"

    except Exception as e:
        return None

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # LANGKAH 1: Dapatkan Link Download API
        download_url = create_direct_link(MY_ONEDRIVE_LINK)
        
        if not download_url:
            return pd.DataFrame(), "Gagal memproses Link OneDrive."

        # LANGKAH 2: Download File
        headers = {"User-Agent": "Mozilla/5.0"}
        
        # Timeout 60 detik (API butuh waktu resolve)
        response = requests.get(download_url, headers=headers, timeout=60)
        
        if response.status_code != 200:
            return pd.DataFrame(), f"Gagal Akses (Code: {response.status_code}). Pastikan izin file 'Anyone'."

        # LANGKAH 3: Baca Excel
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet tanpa header
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "Format file rusak atau bukan Excel (.xlsx)."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # LANGKAH 4: Scanning Data (Mencari Tabel Harga)
        for sheet_name, df in xls.items():
            # Scan 50 baris pertama tiap sheet
            for i, row in df.head(50).iterrows():
                row_text = " ".join(row.astype(str).lower())
                
                # Ciri-ciri tabel: ada kata "berat" dan "end user"
                if "berat" in row_text and "end user" in row_text:
                    
                    # Set Header
                    df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                    data = df.iloc[i+1:].copy()
                    
                    # Cari Kolom Target
                    c_berat = next((c for c in df.columns if "berat" in c), None)
                    c_jual = next((c for c in df.columns if "end user" in c), None)
                    c_stok = next((c for c in df.columns if "stock" in c or "stok" in c), None)
                    
                    if c_berat and c_jual:
                        # Bersihkan Angka
                        data["weight_g"] = data[c_berat].apply(lambda x: _clean_number(x, is_float=True))
                        data["sell_idr"] = data[c_jual].apply(lambda x: _clean_number(x, is_float=False))
                        
                        # Stok
                        if c_stok:
                            data["stock"] = data[c_stok].fillna("Ready")
                        else:
                            data["stock"] = "Ready"
                        
                        # Filter (Hanya harga > 0)
                        valid = data[(data["weight_g"] > 0) & (data["sell_idr"] > 0)].copy()
                        
                        if not valid.empty:
                            # Cari Info Tambahan (Tanggal & Buyback)
                            full_text = " ".join(df.astype(str).values.flatten()).lower()
                            
                            # Cari Tanggal (Format: 07 Feb 2024)
                            dt = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", full_text)
                            if dt: label += f" — {dt.group(1).title()}"
                            
                            # Cari Buyback
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
            return pd.DataFrame(), "Tabel harga tidak ditemukan di file Excel."

        return final_df.sort_values("weight_g").reset_index(drop=True), label

    except Exception as e:
        return pd.DataFrame(), f"Error System: {str(e)}"

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
