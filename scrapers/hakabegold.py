import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# =========================================================
# DATA KUNCI (DIBACA DARI FILE HTLM.TXT YANG ANDA KIRIM)
# =========================================================
# Kita melewati proses scraping website dan langsung pakai link yang tertanam di sana.
CID = "f82ea6cd27a31b67"
TOKEN = "UQRnG6MnzaYuIID4agAAAAAAAJmymdJnSywKmuw"

# Dummy variable agar app.py tidak error
URL_HAKABEGOLD = f"https://1drv.ms/x/c/{CID}/{TOKEN}"

def get_excel_content(cid, token) -> requests.Response:
    """
    Mencoba 3 metode download berbeda secara berurutan.
    Jika satu gagal, coba yang lain.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br"
    }

    # METODE 1: Link 1drv.ms dengan parameter download
    # Ini metode paling modern.
    url_1 = f"https://1drv.ms/x/c/{cid}/{token}?download=1"
    try:
        # allow_redirects=True sangat PENTING di sini
        r = requests.get(url_1, headers=headers, timeout=30, allow_redirects=True)
        if r.status_code == 200 and "text/html" not in r.headers.get("Content-Type", "").lower():
            return r
    except: pass

    # METODE 2: Link onedrive.live.com dengan format 'download'
    # Kita rakit ulang linknya secara manual
    # resid biasanya formatnya: CID (huruf besar) + "!106"
    resid = cid.upper() + "!106"
    url_2 = f"https://onedrive.live.com/download?cid={cid}&resid={resid}&authkey={token}"
    try:
        r = requests.get(url_2, headers=headers, timeout=30)
        if r.status_code == 200 and "text/html" not in r.headers.get("Content-Type", "").lower():
            return r
    except: pass

    # METODE 3: Link onedrive.live.com Alternatif (Tanpa CID di depan)
    url_3 = f"https://onedrive.live.com/download?resid={resid}&authkey={token}"
    try:
        r = requests.get(url_3, headers=headers, timeout=30)
        return r # Return apa adanya (terakhir)
    except: pass
    
    return None

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # --- LANGKAH 1: Download File (Bruteforce) ---
        response = get_excel_content(CID, TOKEN)
        
        if not response:
            return pd.DataFrame(), "HK Logam Mulia — Gagal koneksi (Network Error)"
            
        if response.status_code != 200:
            return pd.DataFrame(), f"HK Logam Mulia — Gagal Download (Code: {response.status_code})"

        # Cek apakah isinya HTML
        if "text/html" in response.headers.get("Content-Type", "").lower():
             return pd.DataFrame(), "HK Logam Mulia — Gagal. Link mengarah ke Web View, bukan File Excel."

        # --- LANGKAH 2: Proses Excel ---
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "HK Logam Mulia — File rusak atau format bukan Excel valid."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # --- LANGKAH 3: Scanning Data ---
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
            return pd.DataFrame(), "HK Logam Mulia — Struktur tabel Excel berubah/tidak ditemukan."

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
