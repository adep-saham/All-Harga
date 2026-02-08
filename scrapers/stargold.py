from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# URL referensi (tetap sesuai app.py)
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser cerdas untuk Stargold.
    1. Mencoba menggunakan html yang dikirim app.py.
    2. Jika kosong, mencari file 'source web.txt' atau 'htlm.txt' di berbagai lokasi.
    3. Mengekstrak data harga Antam, UBS, dan Stargold dari HTML tersebut.
    """
    final_html = html
    source_label = "Live/Provided"

    # --- TAHAP 1: RADAR PENCARIAN FILE ---
    if not final_html or len(final_html) < 500:
        # Daftar nama file yang mungkin Anda gunakan
        target_files = ["source web.txt", "htlm.txt"]
        
        # Daftar lokasi pencarian (Folder utama, folder scrapers, folder saat ini)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(current_dir)
        search_paths = [root_dir, current_dir, os.getcwd()]
        
        found_content = ""
        found_file_name = ""
        
        for directory in search_paths:
            for filename in target_files:
                path = os.path.join(directory, filename)
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
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
            # Jika tetap gagal, coba fetch (kemungkinan besar gagal karena firewall)
            try:
                import requests
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(URL_STARGOLD, timeout=10, headers=headers)
                final_html = resp.text
                source_label = "Live Web"
            except:
                return pd.DataFrame(), "Semua jalur buntu: Koneksi ditolak & file TXT tidak ditemukan di root folder."

    # --- TAHAP 2: EKSTRAKSI DATA (PARSING) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Cari semua tabel di dalam HTML
        tables = soup.find_all("table")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                # Berdasarkan file Anda: td[0]=Produk, td[1]=Jual, td[2]=Buyback
                if len(cols) >= 3:
                    name_text = cols[0].get_text(strip=True).lower()
                    sell_text = cols[1].get_text(strip=True)
                    buyback_text = cols[2].get_text(strip=True)

                    # Filter baris yang mengandung satuan berat 'gr'
                    if "gr" in name_text:
                        try:
                            # 1. Tentukan Vendor
                            vendor = "STARGOLD"
                            if "antam" in name_text: vendor = "ANTAM"
                            elif "ubs" in name_text: vendor = "UBS"
                            elif "emaskita" in name_text: vendor = "EMASKITA"

                            # 2. Bersihkan Berat (Handle 0,1 gr atau 0.1 gr)
                            w_str = name_text.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka saja (biasanya di bagian akhir string produk)
                            w_val = float(w_str.split()[-1])

                            # 3. Bersihkan Harga (Hanya ambil angka)
                            s_val = "".join(filter(str.isdigit, sell_text))
                            b_val = "".join(filter(str.isdigit, buyback_text))

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
            return pd.DataFrame(), f"Data kosong di {source_label}. Cek apakah isi file benar."

        # Finalisasi DataFrame sesuai kebutuhan app.py
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
