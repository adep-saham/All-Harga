from __future__ import annotations
import os
import pandas as pd
import re
import glob
from bs4 import BeautifulSoup

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    final_html = html
    source_label = "Live Web"

    # --- 1. AMBIL SOURCE ---
    if not final_html or len(final_html) < 500:
        potential_files = glob.glob("Source Web*.txt") + glob.glob("source web*.txt")
        if potential_files:
            target_file = sorted(potential_files)[-1]
            try:
                with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                    final_html = f.read()
                source_label = os.path.basename(target_file)
            except Exception as e:
                return pd.DataFrame(), f"Error Baca File: {str(e)}"
        
        if not final_html:
            return pd.DataFrame(), "Gagal: File 'Source Web' tidak ditemukan."

    # --- 2. EKSTRAKSI ---
    try:
        soup = BeautifulSoup(final_html, 'html.parser')
        
        # Cari Last Update (Regex lebih fleksibel)
        extracted_update = "N/A"
        text_full = soup.get_text()
        update_match = re.search(r"Last Update\s*:\s*([\d/]+\s*[\d:]+)", text_full)
        if update_match:
            extracted_update = f"{update_match.group(1)} (via {source_label})"

        all_data = []
        
        # Cari semua judul (h2, h3, atau div class section-title)
        tags = soup.find_all(['h2', 'h3', 'div', 'b', 'strong'])
        
        for tag in tags:
            tag_text = tag.get_text(strip=True).upper()
            
            # Kita hanya proses jika ada kata kunci vendor utama
            target_vendors = ["STARGOLD", "ANTAM", "EMASKITA", "EMASKU", "UBS", "LOTUS", "WARIS"]
            matched_vendor = next((v for v in target_vendors if v in tag_text), None)
            
            if matched_vendor:
                # Cari tabel terdekat setelah judul ini
                table = tag.find_next('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cols = tr.find_all('td')
                        if len(cols) >= 3:
                            try:
                                # Kolom 0: Berat (Hapus semua kecuali angka dan koma/titik)
                                raw_w = cols[0].get_text(strip=True).replace(",", ".")
                                weight_match = re.findall(r"[-+]?\d*\.\d+|\d+", raw_w)
                                if not weight_match: continue
                                weight_val = float(weight_match[0])

                                # Kolom 1 & 2: Harga (Hapus semua kecuali angka)
                                sell_val = "".join(re.findall(r'\d+', cols[1].get_text()))
                                buy_val = "".join(re.findall(r'\d+', cols[2].get_text()))

                                if sell_val:
                                    all_data.append({
                                        "vendor": matched_vendor,
                                        "weight_g": weight_val,
                                        "sell_idr": int(sell_val),
                                        "buyback_idr": int(buy_val) if buy_val else 0,
                                        "source_update": extracted_update
                                    })
                            except: continue

        if not all_data:
            return pd.DataFrame(), f"Data tidak ditemukan. Cek isi file {source_label}"

        # --- 3. CLEANING ---
        df = pd.DataFrame(all_data)
        # Hapus baris yang mungkin sampah (berat 0 atau harga 0)
        df = df[(df['weight_g'] > 0) & (df['sell_idr'] > 0)]
        # Hilangkan duplikat
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"], keep="first")
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        return df, extracted_update

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
