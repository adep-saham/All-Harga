from __future__ import annotations
import os
import pandas as pd
import re
from datetime import datetime
from bs4 import BeautifulSoup

# Variabel wajib untuk app.py
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser khusus untuk struktur HTML Stargold dengan ekstraksi waktu update resmi.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. PENCARIAN FILE ---
    if not final_html or len(final_html) < 500:
        target_file = "source web.txt"
        possible_paths = [
            os.path.join("/mount/src/all-harga", target_file),
            target_file,
            os.path.join(os.getcwd(), target_file)
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    final_html = f.read()
                source_label = f"File ({target_file})"
                break
        
        if not final_html:
            return pd.DataFrame(), f"Gagal: File '{target_file}' tidak ditemukan."

    # --- 2. EKSTRAKSI DATA ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        
        # -------------------------------------------------
        # MENCARI INFO LAST UPDATE (UPDATE BARU)
        # -------------------------------------------------
        # Mencari teks yang mengandung "Last Update" di seluruh halaman
        update_tag = soup.find(string=re.compile(r"Last Update", re.IGNORECASE))
        if update_tag:
            # Membersihkan teks agar hanya mengambil bagian "Last Update : ..."
            raw_update = update_tag.strip()
            # Menghapus karakter aneh jika ada
            extracted_update = re.sub(r'\s+', ' ', raw_update)
        else:
            # Fallback jika tidak ditemukan di HTML
            extracted_update = f"Fetched: {datetime.now().strftime('%d/%m/%y %H:%M:%S')}"

        all_data = []

        # Cari setiap blok pembungkus tabel (compare-page-wrapper)
        sections = soup.find_all("div", class_="compare-page-wrapper")
        
        for section in sections:
            title_tag = section.find("h2", class_="title")
            if not title_tag:
                continue
            
            vendor_name = title_tag.get_text(strip=True).upper()
            table = section.find("table")
            if not table:
                continue
                
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if not cols or "Berat" in row.get_text():
                    continue
                
                if len(cols) >= 3:
                    try:
                        # Parsing berat dan harga
                        weight_text = cols[0].find("p").get_text(strip=True) if cols[0].find("p") else cols[0].get_text(strip=True)
                        weight_val = float(weight_text.replace(",", "."))

                        sell_text = cols[1].find("p").get_text(strip=True) if cols[1].find("p") else cols[1].get_text(strip=True)
                        sell_val = "".join(filter(str.isdigit, sell_text))

                        buyback_text = cols[2].find("p").get_text(strip=True) if cols[2].find("p") else cols[2].get_text(strip=True)
                        buyback_val_str = "".join(filter(str.isdigit, buyback_text))
                        buyback_val = int(buyback_val_str) if buyback_val_str else 0

                        if sell_val:
                            all_data.append({
                                "vendor": vendor_name,
                                "weight_g": weight_val,
                                "sell_idr": int(sell_val),
                                "buyback_idr": buyback_val
                            })
                    except:
                        continue

        if not all_data:
            return pd.DataFrame(), f"Data kosong di {source_label}."

        # --- 3. FINALISASI ---
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        # Menggabungkan label sumber dengan waktu update resmi
        final_label = f"StarGold ({source_label}) - {extracted_update}"
        return df, final_label

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
