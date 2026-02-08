import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# =========================================================
# LINK BERSIH (HASIL DECODE DARI LINK PANJANG ANDA)
# =========================================================
CLEAN_LINK = "https://1drv.ms/x/c/f82ea6cd27a31b67/UQRnG6MnzaYuIID4agAAAAAAJmymdJnSywKmuw"

# Dummy variable
URL_HAKABEGOLD = CLEAN_LINK

def get_direct_download_url(short_link):
    """
    Mengubah link pendek 1drv.ms menjadi link download file (.xlsx)
    dengan cara mengikuti redirect dan memanipulasi URL akhir.
    """
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 1. Ikuti Redirect (PENTING: allow_redirects=True)
        # Kita biarkan OneDrive melempar kita ke alamat aslinya
        response = session.get(short_link, headers=headers, timeout=30, allow_redirects=True)
        final_url = response.url
        
        # 2. Manipulasi URL Akhir
        # Jika URL mengandung 'onedrive.live.com', ubah mode jadi download
        if "onedrive.live.com" in final_url:
            # Ganti '/view.aspx', '/edit.aspx', atau '/redir.aspx' menjadi '/download'
            download_url = re.sub(r"/(view|edit|redir|embed)\.aspx", "/download", final_url)
            # Bersihkan parameter query yang tidak perlu
            return download_url.split("?")[0] + "?download=1"
            
        # Fallback: Jika masih di 1drv.ms, tempel parameter download
        return short_link + "?download=1"

    except Exception as e:
        print(f"Error resolving link: {e}")
        return short_link

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # LANGKAH 1: Dapatkan Link Download Asli
        download_url = get_direct_download_url(CLEAN_LINK)
        
        # LANGKAH 2: Download File
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(download_url, headers=headers, timeout=60)
        
        if response.status_code != 200:
            return pd.DataFrame(), f"Gagal Akses (Code: {response.status_code})"

        # LANGKAH 3: Baca Excel
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet (karena data ada di Sheet2)
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "Link valid, tapi format file bukan Excel (.xlsx)."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # LANGKAH 4: Scanning Data
        for sheet_name, df in xls.items():
            # Scan 50 baris pertama
            for i, row in df.head(50).iterrows():
                row_text = " ".join(row.astype(str).lower())
                
                # Ciri-ciri tabel: ada kata "berat" dan "end user"
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
