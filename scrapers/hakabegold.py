import pandas as pd
import requests
import base64
import re
from io import BytesIO
from typing import Tuple

# =========================================================
# PASTE LINK "SHARE" DARI ONEDRIVE ANDA DI SINI
# =========================================================
# Contoh: "https://1drv.ms/x/s!AmX_..." atau link panjang onedrive.live.com
# Pastikan settingannya "Anyone with the link" (Siapa saja)
MY_ONEDRIVE_LINK = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8?e=GMfdQD"

# Dummy variable
URL_HAKABEGOLD = MY_ONEDRIVE_LINK

def create_direct_link(share_url):
    """
    Mengubah Link Share OneDrive (Web View) menjadi Link Download API (Direct).
    Teknik: Menggunakan OneDrive API v1.0 dengan encoding Base64.
    """
    try:
        # 1. Bersihkan URL
        if not share_url or "http" not in share_url: return None
        
        # 2. Base64 Encoding sesuai standar Microsoft API
        #    - Encode URL ke Base64
        #    - Ganti karakter '+' jadi '-' dan '/' jadi '_'
        #    - Hapus padding '=' di akhir
        #    - Tambahkan prefix 'u!' di depan
        base64_value = base64.b64encode(share_url.encode("utf-8")).decode("utf-8")
        encoded_url = "u!" + base64_value.rstrip("=").replace("/", "_").replace("+", "-")
        
        # 3. Buat URL API Download
        api_url = f"https://api.onedrive.com/v1.0/shares/{encoded_url}/root/content"
        return api_url
    except Exception as e:
        print(f"Error converting link: {e}")
        return share_url

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # --- LANGKAH 1: Convert Link Share jadi Link Download ---
        download_url = create_direct_link(MY_ONEDRIVE_LINK)
        
        if not download_url:
            return pd.DataFrame(), "Link OneDrive belum diisi di script."

        # --- LANGKAH 2: Download File ---
        headers = {"User-Agent": "Mozilla/5.0"}
        # Timeout agak lama karena API butuh waktu resolve
        response = requests.get(download_url, headers=headers, timeout=60)

        if response.status_code != 200:
            return pd.DataFrame(), f"Gagal Akses OneDrive (Code: {response.status_code}). Pastikan Link diset ke 'Anyone'."

        # --- LANGKAH 3: Proses Excel ---
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "Link benar, tapi format file rusak/bukan Excel."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # --- LANGKAH 4: Scanning Data ---
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
                            
                            # Cari Tanggal & Buyback
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
            return pd.DataFrame(), "Tabel harga tidak ditemukan di file Excel Anda."

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
