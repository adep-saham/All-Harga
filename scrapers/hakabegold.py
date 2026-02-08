import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# =========================================================
# LINK RAKITAN MANUAL (HASIL EKSTRAK DARI DATA ANDA)
# =========================================================
# Kita menggabungkan Resid + Authkey untuk bypass halaman Web View.
RESID = "F82EA6CD27A31B67!106"
AUTHKEY = "UQRnG6MnzaYuIID4agAAAAAAJmymdJnSywKmuw"

# Link ini akan langsung memicu download file .xlsx
MANUAL_LINK = f"https://onedrive.live.com/download?resid={RESID}&authkey={AUTHKEY}"

# Dummy variable
URL_HAKABEGOLD = MANUAL_LINK

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # 1. Download File
        # Gunakan User-Agent standar agar tidak diblokir
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Timeout 30 detik sudah cukup untuk direct download
        response = requests.get(MANUAL_LINK, headers=headers, timeout=30)
        
        # Cek Status
        if response.status_code != 200:
            return pd.DataFrame(), f"HK Logam Mulia — Gagal Download (Code: {response.status_code})"

        # Cek Header Content-Type (Pastikan bukan HTML)
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
             return pd.DataFrame(), "HK Logam Mulia — Gagal. Token AuthKey mungkin sudah kadaluarsa."

        # 2. Baca Excel
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet
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
                        
                        # Filter Data (Harga > 0)
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
            return pd.DataFrame(), "HK Logam Mulia — Struktur tabel Excel berubah."

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
