import pandas as pd
import requests
import re
from urllib.parse import urlparse, parse_qs
from io import BytesIO
from typing import Tuple

# Link OneDrive Anda
MY_SHORT_LINK = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8"

# Dummy
URL_HAKABEGOLD = MY_SHORT_LINK

def get_real_download_link(short_url):
    """
    Fungsi Detektif:
    1. Mengikuti link pendek sampai ke alamat asli.
    2. Mengekstrak 'resid' dan 'authkey' dari alamat asli.
    3. Membangun link download yang bersih.
    """
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 1. Ikuti Redirect (PENTING: allow_redirects=True)
        # Kita biarkan dia berjalan sampai mentok ke URL onedrive.live.com...
        print("Resolving URL...")
        response = session.get(short_url, headers=headers, timeout=30, allow_redirects=True)
        final_url = response.url
        print(f"URL Akhir: {final_url}")
        
        # 2. Parsing URL untuk mencari parameter kunci
        parsed = urlparse(final_url)
        params = parse_qs(parsed.query)
        
        # Kita cari resid dan authkey
        resid = params.get('resid', [None])[0]
        authkey = params.get('authkey', [None])[0]
        
        # JIKA GAGAL PARSING (Mungkin format URL beda), KITA PAKAI LOGIKA BRUTEFORCE
        if not resid or not authkey:
            # Coba cari resid dari path (kadang ada di path URL)
            # Biasanya formatnya CID + ! + Nomor
            cid_match = re.search(r'cid=([a-zA-Z0-9]+)', final_url)
            if cid_match:
                # Tebakan jitu: resid biasanya CID + "!106" atau "!105" untuk file Excel
                cid = cid_match.group(1)
                resid = f"{cid.upper()}!106" 
            
            # Cari authkey di string URL (biasanya diawali !)
            if not authkey:
                # Token authkey di link Anda tadi ada di belakang
                # Kita coba ambil dari path short link jika perlu
                # Tapi mari kita coba paksa download dari URL akhir dulu
                return final_url.replace("redir", "download").replace("view", "download").replace("edit", "download")

        # 3. Rakit Link Download Bersih
        # Ini adalah format 'Legend' yang paling disukai Python
        if resid and authkey:
            clean_link = f"https://onedrive.live.com/download?resid={resid}&authkey={authkey}"
            return clean_link
            
        # Fallback terakhir: Tambah ?download=1 di URL akhir
        return final_url + "&download=1"

    except Exception as e:
        print(f"Error resolving: {e}")
        return short_url

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # LANGKAH 1: Dapatkan Link Download Asli
        download_url = get_real_download_link(MY_SHORT_LINK)
        print(f"Menggunakan Link Download: {download_url}")
        
        # LANGKAH 2: Download File
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(download_url, headers=headers, timeout=60)
        
        if response.status_code != 200:
            return pd.DataFrame(), f"Gagal Akses (Code: {response.status_code})"

        # Cek Header (Anti HTML)
        if "text/html" in response.headers.get("Content-Type", "").lower():
             return pd.DataFrame(), "Gagal. Masih diarahkan ke Web View (HTML). Coba perbarui Link Share."

        # LANGKAH 3: Baca Excel
        try:
            xls_data = BytesIO(response.content)
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "Format file rusak/bukan Excel valid."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # LANGKAH 4: Scanning Data
        for sheet_name, df in xls.items():
            for i, row in df.head(50).iterrows():
                row_text = " ".join(row.astype(str).lower())
                
                if "berat" in row_text and "end user" in row_text:
                    df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                    data = df.iloc[i+1:].copy()
                    
                    c_berat = next((c for c in df.columns if "berat" in c), None)
                    c_jual = next((c for c in df.columns if "end user" in c), None)
                    c_stok = next((c for c in df.columns if "stock" in c or "stok" in c), None)
                    
                    if c_berat and c_jual:
                        data["weight_g"] = data[c_berat].apply(lambda x: _clean_number(x, is_float=True))
                        data["sell_idr"] = data[c_jual].apply(lambda x: _clean_number(x, is_float=False))
                        if c_stok: data["stock"] = data[c_stok].fillna("Ready")
                        else: data["stock"] = "Ready"
                        
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
            return pd.DataFrame(), "Tabel harga tidak ditemukan."

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
