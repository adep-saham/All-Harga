from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Jalur Anti-Blokir:
    1. Mencoba akses Live dengan sidik jari Chrome.
    2. Jika gagal, mencari file 'source web.txt' atau 'htlm.txt' di semua folder.
    """
    final_html = html
    source_label = "Live Web"

    # --- JALUR 1: USAHA PENEMBUSAN LIVE ---
    if not final_html or len(final_html) < 100:
        try:
            # Menggunakan sidik jari Chrome 120
            response = requests.get(
                URL_STARGOLD,
                impersonate="chrome",
                timeout=15,
                headers={
                    "referer": "https://www.google.com/",
                    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8",
                }
            )
            response.raise_for_status()
            final_html = response.text
        except Exception:
            # --- JALUR 2: RADAR FILE (Mencari source web.txt atau htlm.txt) ---
            current_script_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(current_script_dir)
            
            # Daftar file yang mungkin Anda unggah
            possible_filenames = ["source web.txt", "htlm.txt"]
            # Daftar lokasi yang mungkin (Folder utama, folder scrapers, atau folder kerja)
            possible_dirs = [root_dir, current_script_dir, os.getcwd()]
            
            found_path = None
            for d in possible_dirs:
                for f_name in possible_filenames:
                    p = os.path.join(d, f_name)
                    if os.path.exists(p):
                        found_path = p
                        break
                if found_path: break
            
            if found_path:
                with open(found_path, "r", encoding="utf-8") as f:
                    final_html = f.read()
                source_label = f"Offline ({os.path.basename(found_path)})"
            else:
                return pd.DataFrame(), "Semua jalur buntu: Koneksi ditolak & file TXT tidak ditemukan di root folder."

    # --- JALUR 3: EKSTRAKSI DATA (PARSER) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Target: Tabel dengan class table-sm (Sesuai source web.txt Anda)
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    # Ambil teks mentah
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Filter: Hanya baris yang ada tulisan 'gr'
                    if "gr" in raw_name:
                        try:
                            # Tentukan Vendor
                            vendor = "STARGOLD"
                            if "antam" in raw_name: vendor = "ANTAM"
                            elif "ubs" in raw_name: vendor = "UBS"
                            elif "emaskita" in raw_name: vendor = "EMASKITA"

                            # Bersihkan Berat (Indo: 0,1 gr -> 0.1)
                            w_str = raw_name.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka desimal terakhir dari string
                            w_val = float(w_str.split()[-1])

                            # Bersihkan Harga (Hanya ambil angka)
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
            return pd.DataFrame(), f"Data kosong di {source_label}. Periksa format HTML."

        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
