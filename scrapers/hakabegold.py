import pandas as pd
from playwright.sync_api import sync_playwright
import time
from io import BytesIO

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

def parse_hakabegold(dummy_html=""):
    # Link download langsung dari OneDrive
    direct_link = "https://onedrive.live.com/download?resid=7181A7DF3EAB3581!106&authkey=!AI3AF18"
    
    try:
        with sync_playwright() as p:
            # Jalankan browser tanpa jendela (headless)
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Buka link download
            response = page.goto(direct_link, timeout=60000)
            time.sleep(5) # Tunggu sebentar untuk redirect
            
            # Ambil konten file
            content = response.body()
            browser.close()
            
            if b"PK" not in content[:4]: # Cek apakah ini file zip/xlsx valid
                return pd.DataFrame(), "HK Logam Mulia — OneDrive masih memblokir (Security Challenge)"

            # Baca Excel
            df_raw = pd.read_excel(BytesIO(content), engine="openpyxl", header=None)
            
            # --- Logika Pembersihan Data ---
            # Cari baris yang mengandung "Berat" dan "End User"
            final_data = []
            for i, row in df_raw.iterrows():
                row_str = " ".join(row.astype(str).lower())
                if "berat" in row_str and "end user" in row_str:
                    # Ambil data di bawah header ini
                    subset = df_raw.iloc[i+1:].copy()
                    for _, s_row in subset.iterrows():
                        try:
                            weight = str(s_row[0]).replace("gr", "").strip()
                            price = str(s_row[4]).replace(".", "").replace(",", "").strip()
                            if weight.replace('.','',1).isdigit() and price.isdigit():
                                final_data.append({
                                    "vendor": "HK Logam Mulia",
                                    "weight_g": float(weight),
                                    "sell_idr": int(price),
                                    "buyback_idr": 0, # Sesuaikan jika ada kolom buyback
                                    "stock": "Ready"
                                })
                        except: continue
                    break
            
            if final_data:
                return pd.DataFrame(final_data), "HK Logam Mulia — Berhasil Update"
            return pd.DataFrame(), "HK Logam Mulia — Data tidak ditemukan dalam Excel"

    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Gagal: {str(e)}"
