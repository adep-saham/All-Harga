from __future__ import annotations
import os
import re
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# Variabel wajib untuk app.py
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser 'Regex-Mode': Mencari pola berat dan harga emas secara cerdas
    tanpa bergantung pada struktur tabel yang kaku.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. RADAR PENCARIAN FILE ---
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
            return pd.DataFrame(), f"Gagal: File '{target_file}' tidak ada di folder project."

    # --- 2. EKSTRAKSI DATA (TEKNIK REGEX) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Cari semua baris tabel (tr) di seluruh dokumen
        rows = soup.find_all("tr")
        
        for row in rows:
            cols = row.find_all(["td", "th"])
            if len(cols) >= 2:
                # Ambil teks mentah dari kolom pertama (Produk/Berat)
                text_produk = cols[0].get_text(" ", strip=True).lower()
                
                # Pola Regex: Mencari angka (bisa koma/titik) diikuti kata 'gr' atau 'gram'
                # Contoh: '0,5 gr', '1 gram', '10gr'
                weight_match = re.search(r"(\d+[.,]?\d*)\s*(?:gr|gram)", text_produk)
                
                if weight_match:
                    try:
                        # Ambil angka berat dan ubah koma jadi titik
                        raw_weight = weight_match.group(1).replace(",", ".")
                        weight_val = float(raw_weight)

                        # Tentukan Vendor (Antam/UBS/Stargold)
                        vendor = "STARGOLD"
                        if "antam" in text_produk: vendor = "ANTAM"
                        elif "ubs" in text_produk: vendor = "UBS"
                        elif "emaskita" in text_produk: vendor = "EMASKITA"

                        # Ambil Harga Jual dari kolom kedua
                        sell_text = cols[1].get_text(strip=True)
                        sell_val = "".join(filter(str.isdigit, sell_text))

                        # Ambil Harga Buyback dari kolom ketiga (jika ada)
                        buyback_val = 0
                        if len(cols) >= 3:
                            bb_text = cols[2].get_text(strip=True)
                            bb_digit = "".join(filter(str.isdigit, bb_text))
                            buyback_val = int(bb_digit) if bb_digit else 0

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
            return pd.DataFrame(), "Data tetap kosong. Pastikan isi 'source web.txt' adalah hasil Ctrl+U (View Source)."

        # --- 3. FINALISASI ---
        df = pd.DataFrame(all_data)
        # Hapus jika ada duplikat berat yang sama di vendor yang sama
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        # Urutkan agar rapi di grafik
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
