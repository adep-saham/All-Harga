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

    # --- 1. AMBIL SOURCE (Mencari file 09022026 terbaru) ---
    if not final_html or len(final_html) < 500:
        potential_files = glob.glob("Source Web*.txt") + glob.glob("source web*.txt")
        if potential_files:
            # Mengurutkan nama file secara alfabetis (09022026 > 07022026)
            target_file = sorted(potential_files)[-1]
            try:
                with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                    final_html = f.read()
                source_label = os.path.basename(target_file)
            except Exception as e:
                return pd.DataFrame(), f"Error Baca File: {str(e)}"
        
        if not final_html:
            return pd.DataFrame(), "Gagal: File 'Source Web' tidak ditemukan."

    # --- 2. EKSTRAKSI TANGGAL (Sangat Spesifik) ---
    try:
        # Mencari pola "Last Update : 09/02/26 09:27:39" langsung di HTML mentah
        # Regex ini menangkap format tanggal dan jam secara presisi
        extracted_update = "N/A"
        date_pattern = r"Last Update\s*:\s*([\d/]{8,10}\s+[\d:]{5,8})"
        update_match = re.search(date_pattern, final_html)
        
        if update_match:
            extracted_update = update_match.group(1).strip()
        else:
            # Jika gagal di mentah, coba cari di teks yang sudah bersih
            soup_tmp = BeautifulSoup(final_html, 'html.parser')
            update_match_text = re.search(date_pattern, soup_tmp.get_text())
            if update_match_text:
                extracted_update = update_match_text.group(1).strip()

        # --- 3. EKSTRAKSI DATA TABEL ---
        soup = BeautifulSoup(final_html, 'html.parser')
        all_data = []
        
        # Cari semua judul brand (STARGOLD, ANTAM, dll)
        # Sesuai file Anda: Judul ada di <h2> atau div class section-title
        tags = soup.find_all(['h2', 'h3', 'div', 'b', 'strong'])
        
        for tag in tags:
            tag_text = tag.get_text(strip=True).upper()
            target_vendors = ["STARGOLD", "ANTAM", "EMASKITA", "EMASKU", "UBS", "LOTUS", "WARIS"]
            matched_vendor = next((v for v in target_vendors if v in tag_text), None)
            
            if matched_vendor:
                # Ambil tabel yang muncul setelah judul brand ini
                table = tag.find_next('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cols = tr.find_all('td')
                        if len(cols) >= 3:
                            try:
                                # Kolom 0: Berat
                                raw_w = cols[0].get_text(strip=True).replace(",", ".")
                                weight_match = re.findall(r"[-+]?\d*\.\d+|\d+", raw_w)
                                if not weight_match: continue
                                weight_val = float(weight_match[0])

                                # Kolom 1 & 2: Harga
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
            return pd.DataFrame(), f"Data tidak ditemukan di {source_label}"

        # --- 4. CLEANING & SORTING ---
        df = pd.DataFrame(all_data)
        df = df[(df['weight_g'] > 0) & (df['sell_idr'] > 0)]
        df = df.drop_duplicates(subset=["vendor", "weight_g"], keep="first")
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        return df, extracted_update

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
