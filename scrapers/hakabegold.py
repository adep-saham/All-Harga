import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# =========================================================
# KONFIGURASI KONEKSI ONEDRIVE
# =========================================================
# Saya sudah mengekstrak link bersih dari parameter 'redeem' di link panjang Anda.
# Link ini akan langsung memaksa download tanpa membuka preview web.
URL_HAKABEGOLD = "https://1drv.ms/x/c/f82ea6cd27a31b67/UQRnG6MnzaYuIID4agAAAAAAJmymdJnSywKmuw?download=1"

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # 1. Request file dengan sopan
        headers = {
            # User-Agent browser modern agar tidak dianggap bot
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        
        # Timeout 60 detik karena redirect 1drv.ms kadang butuh waktu
        # allow_redirects=True PENTING agar link pendek diarahkan ke file asli
        response = requests.get(URL_HAKABEGOLD, headers=headers, timeout=60, allow_redirects=True)
        
        # Cek Status Code
        if response.status_code != 200:
            return pd.DataFrame(), f"HK Logam Mulia — Gagal Akses (Code: {response.status_code})"

        # Cek apakah isinya HTML (berarti gagal/masuk halaman login)
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type:
             # Coba cek apakah ada indikasi file dipindah
             return pd.DataFrame(), "HK Logam Mulia — Link mengarah ke Web View, bukan File Excel. Token mungkin expired."

        # 2. Baca Excel
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet karena data bisa pindah-pindah sheet (Link Anda menyebut Sheet2)
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "HK Logam Mulia — File rusak atau format bukan Excel"

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # 3. Scanning Data (Logic Pencarian Tabel)
        # Kita scan setiap sheet untuk mencari kata kunci "berat" dan "end user"
        for sheet_name, df in xls.items():
            # Scan 50 baris pertama di setiap sheet
            for i, row in df.head(50).iterrows():
                row_text = " ".join(row.astype(str).lower())
                
                # KATA KUNCI UTAMA
                if "berat" in row_text and "end user" in row_text:
                    
                    # Set Header
                    df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                    data = df.iloc[i+1:].copy()
                    
                    # Cari Kolom
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
                        
                        # Filter Data Valid
                        valid = data[(data["weight_g"] > 0) & (data["sell_idr"] > 0)].copy()
                        
                        if not valid.empty:
                            # --- Cari Info Tambahan (Tanggal & Buyback) ---
                            full_text = " ".join(df.astype(str).values.flatten()).lower()
                            
                            # Cari Tanggal
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
            return pd.DataFrame(), "HK Logam Mulia — Struktur tabel Excel berubah/tidak ditemukan."

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
