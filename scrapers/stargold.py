from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# Variabel wajib untuk app.py
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser khusus untuk struktur HTML Stargold yang ditemukan di source web.txt.
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

    # --- 2. EKSTRAKSI DATA BERDASARKAN STRUKTUR SOURCE WEB.TXT ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Cari setiap blok pembungkus tabel (compare-page-wrapper)
        sections = soup.find_all("div", class_="compare-page-wrapper")
        
        for section in sections:
            # Cari Nama Vendor (Antam, Stargold, dll) di dalam judul section [cite: 8, 11]
            title_tag = section.find("h2", class_="title")
            if not title_tag:
                continue
            
            vendor_name = title_tag.get_text(strip=True).upper()
            
            # Cari tabel di dalam section tersebut
            table = section.find("table")
            if not table:
                continue
                
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                # Lewati baris header "Berat (gr)", "Harga Jual", dll [cite: 8]
                if not cols or "Berat" in row.get_text():
                    continue
                
                if len(cols) >= 3:
                    try:
                        # Berat ada di dalam <td class="first-column"><p> 
                        weight_text = cols[0].find("p").get_text(strip=True) if cols[0].find("p") else cols[0].get_text(strip=True)
                        weight_val = float(weight_text.replace(",", "."))

                        # Harga Jual ada di <td class="pro-price"><p> pertama 
                        sell_text = cols[1].find("p").get_text(strip=True) if cols[1].find("p") else cols[1].get_text(strip=True)
                        sell_val = "".join(filter(str.isdigit, sell_text))

                        # Harga Buyback ada di <td class="pro-price"><p> kedua 
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
            return pd.DataFrame(), f"Data kosong. Periksa apakah tabel harga ada di {source_label}."

        # --- 3. FINALISASI ---
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
