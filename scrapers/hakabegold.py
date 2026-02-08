import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# URL Website Utama (Tempat kita mencari Link Excel terbaru)
MAIN_WEBSITE = "https://www.logammuliahk.com/"

def get_latest_onedrive_link() -> str:
    """
    Fungsi ini masuk ke website HK Logam Mulia, mencari iframe OneDrive,
    dan mengambil Link Download terbaru secara otomatis.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        # 1. Buka Website Utama
        response = requests.get(MAIN_WEBSITE, headers=headers, timeout=30)
        if response.status_code != 200: return ""
        
        # 2. Cari pola Link OneDrive di dalam HTML
        # Pola: src="https://onedrive.live.com/embed?resid=..."
        # Kita cari 'resid' dan 'authkey'
        html_content = response.text
        
        # Regex untuk menangkap Resid dan Authkey
        match = re.search(r'onedrive\.live\.com/embed\?resid=([A-Za-z0-9!]+)&authkey=([A-Za-z0-9!_\-]+)', html_content)
        
        if match:
            resid = match.group(1)
            authkey = match.group(2)
            # 3. Rakit Link Download Resmi
            # Ubah 'embed' menjadi 'download'
            dynamic_url = f"https://onedrive.live.com/download?resid={resid}&authkey={authkey}"
            return dynamic_url
            
    except Exception as e:
        print(f"Gagal mencari link dinamis: {e}")
        return ""
    
    return ""

# Variabel dummy agar tidak error import di app.py (akan ditimpa oleh fungsi di atas)
URL_HAKABEGOLD = "Dynamic Link (Auto-Detected)"

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # --- LANGKAH 1: Cari Link Terbaru ---
        download_url = get_latest_onedrive_link()
        
        if not download_url:
            return pd.DataFrame(), "HK Logam Mulia — Gagal menemukan Link Excel di website utama."

        # --- LANGKAH 2: Download Excel ---
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(download_url, headers=headers, timeout=60) # Timeout diperlama
        
        if response.status_code != 200:
            return pd.DataFrame(), f"HK Logam Mulia — Gagal Download (Code: {response.status_code})"

        # Cek apakah isinya HTML (berarti gagal)
        if "text/html" in response.headers.get("Content-Type", "").lower():
             return pd.DataFrame(), "HK Logam Mulia — Link mengarah ke Web, bukan Excel."

        # --- LANGKAH 3: Proses Excel ---
        try:
            xls_data = BytesIO(response.content)
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "HK Logam Mulia — File rusak/Bukan Excel Valid"

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # --- LANGKAH 4: Scanning Data (Logic Lama yang sudah stabil) ---
        for sheet_name, df in xls.items():
            for i, row in df.head(50).iterrows(): # Scan 50 baris
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
                        data["stock"] = data[c_stok].fillna("Ready") if c_stok else "Ready"
                        
                        valid = data[(data["weight_g"] > 0) & (data["sell_idr"] > 0)].copy()
                        
                        if not valid.empty:
                            # Ambil Tanggal & Buyback
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
