from __future__ import annotations
import os
import pandas as pd
import re
import glob
from datetime import datetime
from bs4 import BeautifulSoup

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser Stargold yang fleksibel terhadap nama file dan akurat mengambil 'Last Update'.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. PENCARIAN FILE (DIBUAT LEBIH FLEKSIBEL) ---
    if not final_html or len(final_html) < 500:
        # Mencari file .txt apa pun yang mengandung kata 'Source Web' atau 'source web'
        potential_files = glob.glob("Source Web*.txt") + glob.glob("source web*.txt")
        
        target_file = ""
        if potential_files:
            # Ambil file terbaru berdasarkan waktu modifikasi
            target_file = max(potential_files, key=os.path.getmtime)
            with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                final_html = f.read()
            source_label = f"File ({os.path.basename(target_file)})"
        
        if not final_html:
            return pd.DataFrame(), "Gagal: File 'Source Web' tidak ditemukan di server."

    # --- 2. EKSTRAKSI DATA ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        
        # MENCARI INFO LAST UPDATE (MENDUKUNG MULTI-LINE)
        update_tag = soup.find(string=re.compile(r"Last Update", re.IGNORECASE))
        if update_tag:
            # Mengambil teks, menghapus baris baru, dan merapikan spasi ganda
            raw_update = update_tag.parent.get_text(" ", strip=True)
            extracted_update = re.sub(r'\s+', ' ', raw_update)
            # Fokus ambil bagian 'Last Update : DD/MM/YY HH:MM:SS'
            match_date = re.search(r"Last Update\s*:\s*[\d/ :]+", extracted_update)
            if match_date:
                extracted_update = match_date.group(0)
        else:
            extracted_update = f"Fetched: {datetime.now().strftime('%d/%m/%y %H:%M:%S')}"

        all_data = []
        sections = soup.find_all("div", class_="compare-page-wrapper")
        
        for section in sections:
            title_tag = section.find("h2", class_="title")
            if not title_tag: continue
            
            vendor_name = title_tag.get_text(strip=True).upper()
            table = section.find("table")
            if not table: continue
                
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if not cols or "Berat" in row.get_text(): continue
                
                if len(cols) >= 3:
                    try:
                        # Ambil Berat
                        w_text = cols[0].get_text(strip=True)
                        weight_val = float(w_text.replace(",", "."))

                        # Ambil Harga Jual
                        s_text = cols[1].get_text(strip=True)
                        sell_val = "".join(filter(str.isdigit, s_text))

                        # Ambil Harga Buyback
                        b_text = cols[2].get_text(strip=True)
                        buyback_val = "".join(filter(str.isdigit, b_text))

                        if sell_val:
                            all_data.append({
                                "vendor": vendor_name,
                                "weight_g": weight_val,
                                "sell_idr": int(sell_val),
                                "buyback_idr": int(buyback_val) if buyback_val else 0,
                                "source_update": extracted_update # Tambahkan info tanggal sumber
                            })
                    except: continue

        if not all_data:
            return pd.DataFrame(), f"Data kosong di {source_label}."

        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        
        return df, f"StarGold ({source_label}) - {extracted_update}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
