import pandas as pd
import requests
import base64
import re
from io import BytesIO
from typing import Tuple

# =========================================================
# LINK BERSIH (HASIL DECODE DARI TOKEN 'REDEEM' ANDA)
# =========================================================
# Ini adalah link asli yang tersembunyi di balik link panjang tadi.
# Link ini VALID dan bisa diproses oleh API.
TARGET_LINK = "https://1drv.ms/x/c/f82ea6cd27a31b67/UQRnG6MnzaYuIID4agAAAAAAJmymdJnSywKmuw"

# Dummy variable
URL_HAKABEGOLD = TARGET_LINK

def get_api_download_link(share_url):
    """
    Menggunakan OneDrive API v1.0 untuk mengubah Link Share menjadi Link Download Binary.
    Ini adalah cara paling resmi dan stabil untuk bypass Web View.
    """
    try:
        # 1. Encode URL ke Base64
        base64_value = base64.b64encode(share_url.encode("utf-8")).decode("utf-8")
        
        # 2. Format sesuai standar API OneDrive (URL-Safe)
        #    a. Tambah prefix 'u!'
        #    b. Hapus padding '=' di akhir
        #    c. Ganti '/' jadi '_' dan '+' jadi '-'
        encoded_url = "u!" + base64_value.rstrip("=").replace("/", "_").replace("+", "-")
        
        # 3. Panggil API
        # Endpoint ini akan otomatis redirect ke file .xlsx aslinya
        return f"https://api.onedrive.com/v1.0/shares/{encoded_url}/root/content"

    except Exception as e:
        print(f"Error encoding link: {e}")
        return None

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # LANGKAH 1: Dapatkan Link Download dari API
        api_url = get_api_download_link(TARGET_LINK)
        
        if not api_url:
            return pd.DataFrame(), "Gagal memproses link OneDrive."

        # LANGKAH 2: Download File
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Timeout 60 detik
        response = requests.get(api_url, headers=headers, timeout=60)
        
        # API OneDrive jika sukses biasanya redirect (302) lalu memberi file (200)
        if response.status_code != 200:
            return pd.DataFrame(), f"Gagal Akses API (Code: {response.status_code}). Token mungkin expired."

        # LANGKAH 3: Validasi Konten (Anti HTML)
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
             return pd.DataFrame(), "Gagal. API mengembalikan halaman Login (Link butuh autentikasi ulang)."

        # LANGKAH 4: Baca Excel
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet tanpa header
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "Format file rusak atau bukan Excel."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # LANGKAH 5: Scanning Data (Mencari Tabel Harga)
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
            return pd.DataFrame(), "Tabel harga tidak ditemukan (Struktur Excel berubah)."

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
