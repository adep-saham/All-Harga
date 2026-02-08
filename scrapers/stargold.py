from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# URL referensi (tetap sesuai app.py agar tidak error)
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser 'Human-Logic':
    1. Mencari file 'source web.txt' atau 'htlm.txt' di semua folder project.
    2. Membedah isi source code yang Anda tempel secara manual.
    """
    final_html = html
    source_label = "Live Web"

    # --- TAHAP 1: RADAR PENCARIAN FILE ---
    # Jika app.py mengirim string kosong (karena fetch gagal), kita cari file manual Anda
    if not final_html or len(final_html) < 500:
        # Daftar nama file yang mungkin Anda buat (variasi nama)
        filenames = ["source web.txt", "htlm.txt", "source_web.txt"]
        
        # Cari di folder utama, folder scrapers, dan folder saat ini
        curr_dir = os.path.dirname(os.path.abspath(__file__)) # folder scrapers
        root_dir = os.path.dirname(curr_dir)                # folder utama
        
        search_dirs = [root_dir, curr_dir, os.getcwd()]
        
        found_content = ""
        found_name = ""

        for d in search_dirs:
            for f in filenames:
                path = os.path.join(d, f)
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as file:
                        found_content = file.read()
                        found_name = f
                    break
            if found_content: break

        if found_content:
            final_html = found_content
            source_label = f"Manual Copy ({found_name})"
        else:
            return pd.DataFrame(), "Gagal: File 'source web.txt' tidak ditemukan. Pastikan file ada di folder project."

    # --- TAHAP 2: EKSTRAKSI DATA (PARSER) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Mencari tabel harga (biasanya class table-sm di Stargold)
        tables = soup.find_all("table")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                
                # Struktur: [0] Nama/Berat, [1] Jual, [2] Buyback
                if len(cols) >= 3:
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Filter: Hanya baris yang berisi data emas (ada teks 'gr')
                    if "gr" in raw_name:
                        try:
                            # 1. Tentukan Vendor
                            vendor = "STARGOLD"
                            if "antam" in raw_name: vendor = "ANTAM"
                            elif "ubs" in raw_name: vendor = "UBS"
                            elif "emaskita" in raw_name: vendor = "EMASKITA"

                            # 2. Bersihkan Berat: '0,5 gr' -> 0.5
                            # Ganti koma Indonesia jadi titik sistem
                            w_str = raw_name.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka paling belakang (contoh: 'antam 1' -> '1')
                            w_val = float(w_str.split()[-1])

                            # 3. Bersihkan Harga: Ambil angka saja
                            s_val = "".join(filter(str.isdigit, raw_sell))
                            b_val = "".join(filter(str.isdigit, raw_buyback))

                            if s_val:
                                all_data.append({
                                    "vendor": vendor,
                                    "weight_g": w_val,
                                    "sell_idr": int(s_val),
                                    "buyback_idr": int(b_val) if b_val else 0
                                })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), f"Data tidak ditemukan di {source_label}. Periksa isi filenya."

        # Finalisasi DataFrame
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai HTML: {str(e)}"
