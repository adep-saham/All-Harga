import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# Ini link 'Share' resmi dari HK Logam Mulia (format baru 1drv.ms)
# Link ini jika dibuka di browser akan menampilkan Web View.
# TAPI, jika kita tambah '?download=1', dia akan memberikan filenya.
LINK_DATA_LIVE = "https://1drv.ms/x/c/f82ea6cd27a31b67/UQRnG6MnzaYuIID4agAAAAAAJmymdJnSywKmuw?download=1"

# Dummy untuk app.py
URL_HAKABEGOLD = LINK_DATA_LIVE

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # Gunakan Session untuk menangani cookies/redirect Microsoft
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # 1. Download Data
        # allow_redirects=True PENTING! Karena 1drv.ms akan melempar kita ke server download aslinya.
        response = session.get(LINK_DATA_LIVE, headers=headers, timeout=60, allow_redirects=True)
        
        if response.status_code != 200:
            return pd.DataFrame(), f"HK Logam Mulia — Gagal Akses (Status: {response.status_code})"

        # 2. Cek apakah kita malah dapat halaman Login/HTML (Tanda Gagal)
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            return pd.DataFrame(), "HK Logam Mulia — Gagal ambil data (Terhalang Halaman Web View)."

        # 3. Proses Data (Ubah Raw Data jadi Tabel)
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "HK Logam Mulia — Format data rusak/bukan Excel."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # 4. Scanning Sheet (Mencari di mana tabel harga berada)
        for sheet_name, df in xls.items():
            # Cek 50 baris pertama
            for i, row in df.head(50).iterrows():
                row_text = " ".join(row.astype(str).lower())
                
                # KATA KUNCI: "berat" dan "end user"
                if "berat" in row_text and "end user" in row_text:
                    
                    # Set Header Tabel
                    df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                    data = df.iloc[i+1:].copy()
                    
                    # Identifikasi Kolom
                    c_berat = next((c for c in df.columns if "berat" in c), None)
                    c_jual = next((c for c in df.columns if "end user" in c), None)
                    c_stok = next((c for c in df.columns if "stock" in c or "stok" in c), None)
                    
                    if c_berat and c_jual:
                        # Bersihkan Angka
                        data["weight_g"] = data[c_berat].apply(lambda x: _clean_number(x, is_float=True))
                        data["sell_idr"] = data[c_jual].apply(lambda x: _clean_number(x, is_float=False))
                        
                        if c_stok:
                            data["stock"] = data[c_stok].fillna("Ready")
                        else:
                            data["stock"] = "Ready"
                        
                        # Ambil data yang valid saja (Harga > 0)
                        valid = data[(data["weight_g"] > 0) & (data["sell_idr"] > 0)].copy()
                        
                        if not valid.empty:
                            # Cari Info Tanggal & Buyback dari teks sekitar
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
            return pd.DataFrame(), "HK Logam Mulia — Data tidak ditemukan (Struktur Excel berubah)."

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
