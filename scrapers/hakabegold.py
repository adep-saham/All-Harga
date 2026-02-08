import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# Kita akan cari linknya langsung dari sumbernya
SOURCE_WEBSITE = "https://www.logammuliahk.com/"
# Variable dummy biar app.py gak error
URL_HAKABEGOLD = SOURCE_WEBSITE

def get_live_download_link():
    """
    Fungsi ini bertugas menjadi 'Detektif'.
    Dia akan masuk ke website HK Logam Mulia, mencari iframe Excel,
    dan mengambil link download yang valid saat ini juga.
    """
    try:
        # 1. Buka Website Utama
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(SOURCE_WEBSITE, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return None, "Gagal membuka website logammuliahk.com"

        html = response.text
        
        # 2. Cari Link OneDrive yang tertanam (Embed) menggunakan Regex
        # Polanya biasanya: src="https://onedrive.live.com/embed?resid=..."
        match = re.search(r'src="(https://onedrive\.live\.com/embed\?[^"]+)"', html)
        
        if match:
            embed_url = match.group(1)
            # 3. UBAH link 'embed' menjadi 'download'
            # Ini trik kuncinya agar file bisa didownload tanpa login
            download_url = embed_url.replace("/embed?", "/download?")
            return download_url, None
            
        return None, "Tidak ditemukan link OneDrive di halaman depan website."
        
    except Exception as e:
        return None, f"Error saat mencari link: {str(e)}"

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # LANGKAH 1: Cari Link Download Terbaru Otomatis
        excel_url, error_msg = get_live_download_link()
        
        if not excel_url:
            return pd.DataFrame(), f"HK Logam Mulia — {error_msg}"

        # LANGKAH 2: Download File Excelnya
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(excel_url, headers=headers, timeout=60)
        
        if r.status_code != 200:
            return pd.DataFrame(), f"HK Logam Mulia — Gagal Download File (Code: {r.status_code})"

        # Cek Header (Pastikan bukan HTML)
        if "text/html" in r.headers.get("Content-Type", "").lower():
            return pd.DataFrame(), "HK Logam Mulia — Link mengarah ke Web, bukan File Excel."

        # LANGKAH 3: Proses Data (Sama seperti sebelumnya)
        try:
            xls_data = BytesIO(r.content)
            # Baca semua sheet
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "HK Logam Mulia — File rusak atau format Excel tidak valid."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # Scanning Sheets
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
                        data["stock"] = data[c_stok].fillna("Ready") if c_stok else "Ready"
                        
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
            return pd.DataFrame(), "HK Logam Mulia — Tabel tidak ditemukan (Format Excel Berubah)."

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
