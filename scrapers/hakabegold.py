import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# =========================================================
# DATA TERBARU DARI LINK ANDA
# =========================================================
# Link: https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8
# CID: 7181a7df3eab3581
# AuthKey: IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8
# =========================================================

CID = "7181a7df3eab3581"
# Kita tebak Resid-nya (Biasanya CID + !106 untuk file utama)
RESID = f"{CID.upper()}!106" 
AUTHKEY = "IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8"

# Link Download Paksa
URL_HAKABEGOLD = f"https://onedrive.live.com/download?resid={RESID}&authkey={AUTHKEY}"

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # 1. Download
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(URL_HAKABEGOLD, headers=headers, timeout=60)

        if response.status_code != 200:
            return pd.DataFrame(), f"Gagal Koneksi (Code: {response.status_code})"
        
        if "text/html" in response.headers.get("Content-Type", "").lower():
            return pd.DataFrame(), "Link mengarah ke HTML (Salah AuthKey/Resid)."

        # 2. Baca Excel
        xls_data = BytesIO(response.content)
        try:
            # Baca semua sheet
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except:
            return pd.DataFrame(), "File rusak/bukan Excel."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        
        # Variabel untuk menampung data mentah (untuk debugging)
        debug_info = []

        # 3. Scanning Data
        for sheet_name, df in xls.items():
            # Simpan 5 baris pertama untuk laporan jika gagal
            debug_info.append(f"Sheet: {sheet_name}\nSample Data:\n{df.head(5).to_string()}\n")

            # Kita Longgarkan Pencarian: Cari kata "berat" ATAU "gram" saja
            for i, row in df.head(50).iterrows():
                row_text = " ".join(row.astype(str).lower())
                
                # LOGIKA BARU: Cukup cari kata "berat" atau "item"
                # Karena kadang "end user" ditulis beda
                if ("berat" in row_text or "gram" in row_text) and ("jual" in row_text or "price" in row_text or "user" in row_text):
                    
                    # Set Header
                    df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                    data = df.iloc[i+1:].copy()
                    
                    # Mapping Kolom Lebih Pintar
                    c_berat = next((c for c in df.columns if "berat" in c or "gram" in c or "weight" in c), None)
                    # Cari kolom harga (bisa 'end user', 'harga', 'jual', 'price')
                    c_jual = next((c for c in df.columns if "user" in c or "jual" in c or "harga" in c or "price" in c), None)
                    c_stok = next((c for c in df.columns if "stok" in c or "stock" in c), None)
                    
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
                            # Cari Buyback
                            full_text = " ".join(df.astype(str).values.flatten()).lower()
                            
                            # Coba cari tanggal
                            dt = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", full_text)
                            if dt: label += f" — {dt.group(1).title()}"

                            # Coba cari buyback
                            bb = re.search(r"buyback.*?(\d[\d\.,]+)", full_text)
                            buyback_val = 0
                            if bb:
                                buyback_val = _clean_number(bb.group(1))
                                label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                            
                            valid["vendor"] = "HK Logam Mulia"
                            valid["buyback_idr"] = (valid["weight_g"] * buyback_val).astype(int)
                            final_df = valid[["vendor", "weight_g", "sell_idr", "buyback_idr", "stock"]]
                            break
            if not final_df.empty: break

        if final_df.empty:
            # FITUR DIAGNOSTIK:
            # Jika kosong, kembalikan Pesan Error berisi Data Mentah
            # Supaya kita tahu harus ubah kata kunci apa
            error_msg = "Tabel tidak dikenali. Ini sampel data Excel-nya:\n" + "\n".join(debug_info[:2])
            return pd.DataFrame(), error_msg

        return final_df.sort_values("weight_g").reset_index(drop=True), label

    except Exception as e:
        return pd.DataFrame(), f"Error: {str(e)}"

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
