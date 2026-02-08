from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# PENTING: Variabel ini harus ada karena dipanggil oleh app.py
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser cerdas untuk membaca data dari 'source web.txt' di Streamlit Cloud.
    """
    final_html = html
    source_label = "Live Web"

    # --- RADAR PENCARIAN FILE ---
    if not final_html or len(final_html) < 500:
        # Nama file yang Anda upload ke GitHub
        target_file = "source web.txt"
        
        # Lokasi standard di Streamlit Cloud
        root_path = "/mount/src/all-harga"
        full_path = os.path.join(root_path, target_file)
        
        # Cek apakah file ada
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                final_html = f.read()
            source_label = f"Offline ({target_file})"
        elif os.path.exists(target_file):
            with open(target_file, "r", encoding="utf-8") as f:
                final_html = f.read()
            source_label = f"Offline ({target_file})"
        else:
            return pd.DataFrame(), f"Gagal: File '{target_file}' tidak ditemukan di GitHub."

    # --- EKSTRAKSI DATA ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Ambil tabel harga
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    if "gr" in raw_name:
                        try:
                            # Tentukan Vendor
                            vendor = "STARGOLD"
                            if "antam" in raw_name: vendor = "ANTAM"
                            elif "ubs" in raw_name: vendor = "UBS"

                            # Bersihkan Berat (0,1 gr -> 0.1)
                            w_str = raw_name.replace("gr", "").replace(",", ".").strip()
                            w_val = float(w_str.split()[-1])

                            # Bersihkan Harga
                            s_val = "".join(filter(str.isdigit, raw_sell))
                            b_val = "".join(filter(str.isdigit, raw_buyback))

                            if s_val:
                                all_data.append({
                                    "vendor": vendor,
                                    "weight_g": w_val,
                                    "sell_idr": int(s_val),
                                    "buyback_idr": int(b_val) if b_val else 0
                                })
                        except: continue

        if not all_data:
            return pd.DataFrame(), f"Data kosong. Periksa isi {target_file}."

        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
