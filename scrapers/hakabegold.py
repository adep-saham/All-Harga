import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# Target Website
SOURCE_WEBSITE = "https://www.logammuliahk.com/"
# Dummy variable agar app.py tidak error import
URL_HAKABEGOLD = SOURCE_WEBSITE

def get_smart_download_link():
    """
    Mencari link OneDrive di website logammuliahk.com dan
    mengubahnya menjadi Link Download Langsung (Bypass Web View).
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 1. Fetch Halaman Utama
        response = requests.get(SOURCE_WEBSITE, headers=headers, timeout=30)
        if response.status_code != 200:
            return None, f"Gagal akses website utama (Code: {response.status_code})"
            
        html = response.text
        
        # 2. Cari iframe OneDrive
        # Pola 1: Link Modern (1drv.ms) -> Kita ekstrak CID dan Token
        # Contoh: https://1drv.ms/x/c/f82ea6cd27a31b67/UQRnG6MnzaYuIID4agAAAAAAAJmymdJnSywKmuw
        match_modern = re.search(r'src=[\'"]https://1drv\.ms/x/c/([a-zA-Z0-9]+)/([a-zA-Z0-9_\-]+).*?[\'"]', html)
        
        if match_modern:
            cid = match_modern.group(1)
            token = match_modern.group(2)
            # REKONSTRUKSI LINK: Gunakan format API lama yang lebih stabil
            # resid biasanya = CID (uppercase) + "!106" (berdasarkan histori file mereka)
            direct_url = f"https://onedrive.live.com/download?resid={cid.upper()}!106&authkey={token}"
            return direct_url, None

        # Pola 2: Link Klasik (onedrive.live.com/embed)
        match_classic = re.search(r'src=[\'"]https://onedrive\.live\.com/embed\?resid=([a-zA-Z0-9!]+)&authkey=([a-zA-Z0-9!_\-]+).*?[\'"]', html)
        
        if match_classic:
            resid = match_classic.group(1)
            authkey = match_classic.group(2)
            direct_url = f"https://onedrive.live.com/download?resid={resid}&authkey={authkey}"
            return direct_url, None

        # Jika tidak ketemu pola spesifik, cari sembarang link 1drv.ms lalu paksa download=1
        match_generic = re.search(r'src=[\'"](https://1drv\.ms/[^\'"]+)[\'"]', html)
        if match_generic:
            raw_url = match_generic.group(1)
            # Bersihkan query params lama, ganti dengan download=1
            clean_url = raw_url.split('?')[0]
            return f"{clean_url}?download=1", None

        return None, "Tidak ditemukan iframe OneDrive yang valid di halaman utama."

    except Exception as e:
        return None, f"Error saat mencari link: {str(e)}"

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # LANGKAH 1: Dapatkan Link Download Cerdas
        download_url, error_msg = get_smart_download_link()
        
        if not download_url:
            return pd.DataFrame(), f"HK Logam Mulia — {error_msg}"

        # LANGKAH 2: Download File
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "*/*"
        }
        # allow_redirects=True sangat penting untuk link 1drv.ms
        response = requests.get(download_url, headers=headers, timeout=60, allow_redirects=True)
        
        if response.status_code != 200:
            return pd.DataFrame(), f"HK Logam Mulia — Gagal Download (Code: {response.status_code})"

        # Cek Content-Type untuk memastikan bukan HTML
        ct = response.headers.get("Content-Type", "").lower()
        if "text/html" in ct:
            return pd.DataFrame(), "HK Logam Mulia — Link mengarah ke Web View (HTML), bukan File Excel. Gagal bypass."

        # LANGKAH 3: Proses Excel
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet karena posisi data bisa berubah
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "HK Logam Mulia — File rusak atau format bukan Excel valid."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # LANGKAH 4: Scanning Data (Logic Stabil)
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
            return pd.DataFrame(), "HK Logam Mulia — Tabel Excel tidak ditemukan (Struktur Berubah)."

        return final_df.sort_values("weight_g").reset_index(drop=True), label

    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Error System: {str(e)}"

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
