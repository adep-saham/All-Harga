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
    Parser Stargold dengan output label tanggal yang bersih.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. PENCARIAN FILE ---
    if not final_html or len(final_html) < 500:
        # Mencari file upload terbaru
        potential_files = glob.glob("Source Web*.txt") + glob.glob("source web*.txt")
        if potential_files:
            target_file = max(potential_files, key=os.path.getmtime)
            with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                final_html = f.read()
            source_label = os.path.basename(target_file)
        
        if not final_html:
            return pd.DataFrame(), "Gagal: File tidak ditemukan."

    # --- 2. EKSTRAKSI DATA ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        
        # Ekstraksi Last Update
        update_tag = soup.find(string=re.compile(r"Last Update", re.IGNORECASE))
        if update_tag:
            # Mengambil teks murni dan merapikan spasi
            raw_text = update_tag.parent.get_text(" ", strip=True)
            clean_text = re.sub(r'\s+', ' ', raw_text)
            
            # Cari pola 'Last Update : 00/00/00 00:00:00'
            match = re.search(r"Last Update\s*:\s*[\d/ :]+", clean_text, re.IGNORECASE)
            if match:
                extracted_update = match.group(0).strip()
            else:
                extracted_update = clean_text
        else:
            extracted_update = f"Update: {datetime.now().strftime('%d/%m/%y %H:%M:%S')}"

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
                        w_text = cols[0].get_text(strip=True)
                        weight_val = float(w_text.replace(",", "."))
                        s_text = "".join(filter(str.isdigit, cols[1].get_text(strip=True)))
                        b_text = "".join(filter(str.isdigit, cols[2].get_text(strip=True)))

                        if s_text:
                            all_data.append({
                                "vendor": vendor_name,
                                "weight_g": weight_val,
                                "sell_idr": int(s_text),
                                "buyback_idr": int(b_text) if b_text else 0,
                                "source_update": extracted_update
                            })
                    except: continue

        if not all_data:
            return pd.DataFrame(), "Data Kosong"

        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g"], keep="first")
        
        # --- PERUBAHAN DI SINI ---
        # Kita hanya mengembalikan extracted_update saja agar labelnya bersih
        return df, extracted_update

    except Exception as e:
        return pd.DataFrame(), f"Error: {str(e)}"
