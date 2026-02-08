from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# URL Sasaran (Kekal untuk rujukan app.py)
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Versi 'Super Radar': 
    Sangat agresif mencari fail TXT anda dan membedah kod sumber manual.
    """
    final_html = html
    source_label = "Live Web"

    # --- TAHAP 1: RADAR PENCARIAN FAIL (LALUAN MANUSIA) ---
    if not final_html or len(final_html) < 500:
        # Nama fail yang mungkin anda gunakan
        target_files = ["source web.txt", "htlm.txt", "source_web.txt"]
        
        # Lokasi Radar: Folder utama, folder scrapers, dan folder kerja semasa
        script_dir = os.path.dirname(os.path.abspath(__file__)) 
        root_dir = os.path.dirname(script_dir)                 
        work_dir = os.getcwd()                                 
        
        paths_to_scan = [work_dir, root_dir, script_dir]
        
        found_content = ""
        found_file_name = ""

        for directory in paths_to_scan:
            for filename in target_files:
                full_path = os.path.join(directory, filename)
                if os.path.exists(full_path):
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            found_content = f.read()
                            found_file_name = filename
                        break
                    except:
                        continue
            if found_content: break

        if found_content:
            final_html = found_content
            source_label = f"Offline ({found_file_name})"
        else:
            # Jika masih gagal, beri maklumat folder supaya user tahu di mana nak letak fail
            files_seen = ", ".join(os.listdir(work_dir)[:10])
            return pd.DataFrame(), f"Gagal: Fail TXT tidak dijumpai. Letakkan 'source web.txt' di {work_dir}. Fail sedia ada: [{files_seen}]"

    # --- TAHAP 2: EKSTRAKSI DATA (TEKNIK VIEW-SOURCE) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Mencari semua jadual (Stargold menggunakan class 'table-sm')
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                
                # Mengikut struktur fail anda: [0] Produk, [1] Jual, [2] Buyback
                if len(cols) >= 3:
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Tapis baris yang mempunyai berat 'gr'
                    if "gr" in raw_name:
                        try:
                            # 1. Kenal Pasti Vendor (Antam/UBS/Stargold)
                            vendor = "STARGOLD"
                            if "antam" in raw_name: vendor = "ANTAM"
                            elif "ubs" in raw_name: vendor = "UBS"
                            elif "emaskita" in raw_name: vendor = "EMASKITA"

                            # 2. Bersihkan Berat (0,1 gr -> 0.1)
                            # Tukar koma kepada titik untuk pengiraan Python
                            w_str = raw_name.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka terakhir (contoh: 'antam 1' jadi '1')
                            w_val = float(w_str.split()[-1])

                            # 3. Bersihkan Harga (Ambil digit sahaja)
                            s_val = "".join(filter(str.isdigit, raw_sell))
                            b_val = "".join(filter(str.isdigit, raw_buyback))

                            if s_val:
                                all_data.append({
                                    "vendor": vendor,
                                    "weight_g": w_val,
                                    "sell_idr": int(s_val),
                                    "buyback_idr": int(b_val) if b_val else 0
                                })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), f"Data tidak dijumpai dalam {source_label}. Pastikan anda salin 'View Source' sepenuhnya."

        # Tukar ke DataFrame dan susun
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Ralat Urai: {str(e)}"
