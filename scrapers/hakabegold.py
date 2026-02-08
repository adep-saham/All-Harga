import re
import pandas as pd
from playwright.sync_api import sync_playwright
from io import BytesIO
from typing import Tuple

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"
# Link Direct Download (Bypass View)
DIRECT_LINK = "https://onedrive.live.com/download?resid=7181A7DF3EAB3581!106&authkey=!AI3AF18"

def _clean_num(val, is_float=False):
    """Pembersih angka super teliti (tahan terhadap typo admin)"""
    if pd.isna(val) or val == "": return 0
    s = str(val).lower().replace("gr", "").replace("gram", "").strip()
    try:
        if is_float:
            # Ganti koma jadi titik (10,5 -> 10.5)
            s = s.replace(",", ".")
            return float(re.findall(r"[-+]?\d*\.\d+|\d+", s)[0])
        else:
            # Ambil angka bulat (Rp 1.000.000 -> 1000000)
            s = s.split(",")[0].split(".")[0] # Buang desimal
            return int(re.sub(r"[^\d]", "", s))
    except:
        return 0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    """
    Menggunakan Playwright Network Request untuk mengambil file biner
    tanpa terdeteksi sebagai Bot Python biasa.
    """
    try:
        with sync_playwright() as p:
            # Luncurkan browser headless
            browser = p.chromium.launch(headless=True)
            
            # Buat context (seperti session browser baru)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            # Gunakan API Request Playwright (Lebih sakti dari requests biasa)
            page = context.new_page()
            response = page.request.get(DIRECT_LINK)
            
            # Cek status
            if response.status != 200:
                browser.close()
                return pd.DataFrame(), f"HK Logam Mulia — Gagal Download (Status: {response.status})"
            
            # Ambil data biner
            file_content = response.body()
            browser.close()

            # Validasi Header File (PK = Zip/Excel)
            if not file_content.startswith(b'PK'):
                return pd.DataFrame(), "HK Logam Mulia — Terblokir (Respon bukan Excel)"

            # --- PROSES EXCEL ---
            xls = pd.read_excel(BytesIO(file_content), sheet_name=None, header=None, engine='openpyxl')
            
            final_df = pd.DataFrame()
            label = "HK Logam Mulia"
            buyback_val = 0
            
            # Scan semua sheet
            for sheet_name, df in xls.items():
                # Scan 50 baris pertama untuk mencari Header
                for i, row in df.head(50).iterrows():
                    row_txt = " ".join(row.astype(str).lower())
                    
                    if "berat" in row_txt and "end user" in row_txt:
                        # Set Header
                        df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                        data = df.iloc[i+1:].copy()
                        
                        # Cari kolom target
                        c_berat = next((c for c in df.columns if "berat" in c), None)
                        c_jual  = next((c for c in df.columns if "end user" in c), None)
                        c_stok  = next((c for c in df.columns if "stok" in c or "stock" in c), None)
                        
                        if c_berat and c_jual:
                            data["weight_g"] = data[c_berat].apply(lambda x: _clean_num(x, True))
                            data["sell_idr"] = data[c_jual].apply(lambda x: _clean_num(x, False))
                            
                            # Jika ada kolom stok
                            if c_stok:
                                data["stock"] = data[c_stok].fillna("Ready")
                            else:
                                data["stock"] = "Ready"

                            # Filter Data Valid
                            valid = data[(data["weight_g"] > 0) & (data["sell_idr"] > 1000)].copy()
                            
                            if not valid.empty:
                                # Cari Metadata (Buyback & Tanggal) di teks sheet
                                full_text = " ".join(df.astype(str).values.flatten()).lower()
                                
                                bb_m = re.search(r"buyback.*?(\d[\d\.,]{6,})", full_text)
                                if bb_m: 
                                    buyback_val = _clean_num(bb_m.group(1))
                                    label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                                
                                dt_m = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", full_text)
                                if dt_m: 
                                    label += f" — {dt_m.group(1).title()}"
                                
                                valid["vendor"] = "HK Logam Mulia"
                                valid["buyback_idr"] = (valid["weight_g"] * buyback_val).astype(int)
                                
                                # Simpan hasil
                                cols = ["vendor", "weight_g", "sell_idr", "buyback_idr", "stock"]
                                final_df = valid[cols]
                                break
                if not final_df.empty: break
            
            if final_df.empty:
                return pd.DataFrame(), "HK Logam Mulia — Struktur Excel berubah/tidak ditemukan"

            return final_df.sort_values("weight_g").reset_index(drop=True), label

    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Error System: {str(e)}"
