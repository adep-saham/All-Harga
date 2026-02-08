from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# PENTING: Jangan hapus variabel ini karena di-import oleh app.py
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser 'Ultra-Flexible':
    Mencari data di semua tabel tanpa bergantung pada nama class yang spesifik.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. RADAR PENCARIAN FILE ---
    if not final_html or len(final_html) < 500:
        target_file = "source web.txt"
        # Cari di folder root Streamlit Cloud atau folder lokal
        possible_paths = [
            os.path.join("/mount/src/all-harga", target_file),
            target_file,
            os.path.join(os.getcwd(), target_file)
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    final_html = f.read()
                source_label = f"Offline ({target_file})"
                break
        
        if not final_html:
            return pd.DataFrame(), f"Gagal: File '{target_file}' tidak ditemukan di GitHub."

    # --- 2. EKSTRAKSI DATA (PARSER TANGGUH) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Ambil SEMUA tabel yang ada, jangan cuma yang punya class 'table-sm'
        tables = soup.find_all("table")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                # Cari semua sel (td atau th)
                cols = row.find_all(["td", "th"])
                
                # Pastikan ada minimal 2 atau 3 kolom (Berat & Harga Jual)
                if len(cols) >= 2:
                    raw_name = cols[0].get_text(" ", strip=True).lower()
                    
                    # Cek apakah baris ini berisi data emas (ada kata 'gr')
                    if "gr" in raw_name:
                        try:
                            # Tentukan Vendor secara cerdas
                            vendor = "STARGOLD"
                            if "antam" in raw_name: vendor = "ANTAM"
                            elif "ubs" in raw_name: vendor = "UBS"
                            elif "emaskita" in raw_name: vendor = "EMASKITA"

                            # 1. Ambil Berat: Ambil angka sebelum 'gr'
                            # Contoh: 'antam 0,5 gr' -> ambil '0,5'
                            w_part = raw_name.split("gr")[0].strip().split()[-1]
                            weight_val = float(w_part.replace(",", "."))

                            # 2. Ambil Harga Jual (Kolom ke-2)
                            sell_text = cols[1].get_text(strip=True)
                            sell_val = "".join(filter(str.isdigit, sell_text))

                            # 3. Ambil Harga Buyback (Kolom ke-3 jika ada)
                            buyback_val = 0
                            if len(cols) >= 3:
                                bb_text = cols[2].get_text(strip=True)
                                bb_val_str = "".join(filter(str.isdigit, bb_text))
                                buyback_val = int(bb_val_str) if bb_val_str else 0

                            if sell_val:
                                all_data.append({
                                    "vendor": vendor,
                                    "weight_g": weight_val,
                                    "sell_idr": int(sell_val),
                                    "buyback_idr": buyback_val
                                })
                        except:
                            continue

        if not all_data:
            # Jika masih kosong, coba cari di dalam elemen div (beberapa web pakai div, bukan table)
            return pd.DataFrame(), "Data tetap kosong. Pastikan Anda meng-copy seluruh View Source (Ctrl+A)."

        # --- 3. FINALISASI DATAFRAME ---
        df = pd.DataFrame(all_data)
        # Hapus baris yang mungkin duplikat
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        # Urutkan berdasarkan vendor dan berat
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
