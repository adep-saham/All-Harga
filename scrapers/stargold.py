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
    Parser Stargold yang otomatis mencari file upload terbaru di server 
    atau memproses HTML yang dikirim langsung.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. PENCARIAN FILE FISIK (Jika html kosong/pendek) ---
    if not final_html or len(final_html) < 500:
        # Mencari semua file TXT yang mengandung kata 'Source Web'
        potential_files = glob.glob("Source Web*.txt") + glob.glob("source web*.txt")
        
        if potential_files:
            # Mengambil file yang memiliki waktu modifikasi terbaru (paling baru di-upload)
            target_file = max(potential_files, key=os.path.getmtime)
            try:
                with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                    final_html = f.read()
                source_label = os.path.basename(target_file)
            except Exception as e:
                return pd.DataFrame(), f"Error Baca File: {str(e)}"
        
        if not final_html:
            return pd.DataFrame(), "Gagal: File 'Source Web' tidak ditemukan di folder server."

    # --- 2. EKSTRAKSI DATA ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        
        # Ekstraksi Label 'Last Update' dari website
        update_tag = soup.find(string=re.compile(r"Last Update", re.IGNORECASE))
        if update_tag:
            # Mengambil teks dari pembungkusnya (parent) dan merapikan spasi/newline
            full_text = update_tag.parent.get_text(" ", strip=True)
            clean_text = re.sub(r'\s+', ' ', full_text)
            
            # Cari pola tanggal 'Last Update : DD/MM/YY HH:MM:SS'
            date_match = re.search(r"Last Update\s*:\s*([\d/ :]+)", clean_text, re.IGNORECASE)
            if date_match:
                extracted_update = f"Last Update: {date_match.group(1).strip()}"
            else:
                extracted_update = clean_text # Fallback ke teks penuh jika pola tidak pas
        else:
            # Jika tidak ada di HTML, gunakan waktu saat ditarik
            extracted_update = f"Fetched: {datetime.now().strftime('%d/%m/%y %H:%M:%S')}"

        all_data = []
        # Cari setiap blok tabel (Stargold menggunakan class compare-page-wrapper)
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
                # Lewati header (yang mengandung kata "Berat")
                if not cols or "Berat" in row.get_text(): continue
                
                if len(cols) >= 3:
                    try:
                        # Berat (Kolom 0)
                        w_text = cols[0].get_text(strip=True)
                        weight_val = float(w_text.replace(",", "."))

                        # Harga Jual (Kolom 1)
                        s_text = "".join(filter(str.isdigit, cols[1].get_text(strip=True)))
                        
                        # Harga Buyback (Kolom 2)
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
            return pd.DataFrame(), f"Data Kosong di {source_label}"

        # Finalisasi DataFrame
        df = pd.DataFrame(all_data)
        # Hapus duplikat per vendor dan berat (ambil harga termurah jika ada ganda)
        df = df.sort_values("sell_idr").drop_duplicates(subset=["vendor", "weight_g"], keep="first")
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        return df, extracted_update

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
