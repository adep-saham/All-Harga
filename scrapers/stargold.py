from __future__ import annotations
import os
import pandas as pd
import re
import glob
from bs4 import BeautifulSoup

# URL resmi sebagai referensi (meskipun data sering ditarik dari file upload)
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser Stargold yang memprioritaskan file Source Web terbaru berdasarkan nama file.
    Logika sorting memastikan tanggal 09 Februari (0902...) dipilih dibanding 07 Februari.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. PENCARIAN FILE LOKAL ---
    # Jika html kosong (saat dipanggil dari app.py tanpa parameter), cari file di folder utama
    if not final_html or len(final_html) < 500:
        # Mencari semua file TXT dengan pola 'Source Web'
        potential_files = glob.glob("Source Web*.txt") + glob.glob("source web*.txt")
        
        if potential_files:
            # PENTING: Diurutkan secara alfabetis. 
            # 'Source Web 09022026.txt' > 'Source Web 07022026.txt'
            target_file = sorted(potential_files)[-1]
            try:
                with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                    final_html = f.read()
                source_label = os.path.basename(target_file)
            except Exception as e:
                return pd.DataFrame(), f"Error Baca File: {str(e)}"
        
        if not final_html:
            return pd.DataFrame(), "Gagal: File 'Source Web' tidak ditemukan."

    # --- 2. EKSTRAKSI DATA ---
    try:
        soup = BeautifulSoup(final_html, 'html.parser')
        
        # Ekstrak label waktu update dari teks halaman
        extracted_update = "N/A"
        # Mencari pola 'Last Update : DD/MM/YY HH:MM:SS'
        update_match = re.search(r"Last Update\s*:\s*([\d/]+\s*[\d:]+)", soup.get_text())
        if update_match:
            extracted_update = update_match.group(1)
            # Menandai apakah data berasal dari file atau live web
            extracted_update = f"{extracted_update} (via {source_label})"

        all_data = []
        
        # Mencari judul vendor (STARGOLD, ANTAM, EMASKITA, dll)
        # File Anda menggunakan h2 atau div class 'section-title'
        titles = soup.find_all(['h2', 'div'], class_='section-title')
        if not titles:
            titles = soup.find_all('h2')

        for title in titles:
            vendor_name = title.get_text(strip=True).upper()
            
            # Abaikan jika teks bukan nama vendor yang valid (sampah scraping)
            if any(x in vendor_name for x in ["DAFTAR", "FOLLOW", "HARGA"]):
                continue
                
            # Mencari tabel yang berada tepat setelah judul vendor
            table = title.find_next('table')
            if table:
                rows = table.find_all('tr')
                for tr in rows:
                    cols = tr.find_all('td')
                    # Baris data valid biasanya punya 3 kolom (Berat, Harga Jual, Buyback)
                    if len(cols) >= 3:
                        try:
                            # Kolom 0: Berat (e.g., "1 gr" atau "0,5 gr")
                            w_text = cols[0].get_text(strip=True).lower().replace("gr", "").strip()
                            weight_val = float(w_text.replace(",", "."))

                            # Kolom 1: Harga Jual (Ambil hanya angka)
                            s_text = "".join(filter(str.isdigit, cols[1].get_text(strip=True)))
                            
                            # Kolom 2: Harga Buyback (Ambil hanya angka)
                            b_text = "".join(filter(str.isdigit, cols[2].get_text(strip=True)))

                            if s_text:
                                all_data.append({
                                    "vendor": vendor_name,
                                    "weight_g": weight_val,
                                    "sell_idr": int(s_text),
                                    "buyback_idr": int(b_text) if b_text else 0,
                                    "source_update": extracted_update
                                })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), f"Data tidak ditemukan di {source_label}"

        # --- 3. CLEANING DATAFRAME ---
        df = pd.DataFrame(all_data)
        
        # Hapus duplikat: jika ada vendor & berat yang sama, ambil yang harga jualnya termurah (first)
        df = df.sort_values("sell_idr").drop_duplicates(subset=["vendor", "weight_g"], keep="first")
        
        # Urutkan berdasarkan Nama Vendor dan Berat (kecil ke besar)
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        return df, extracted_update

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai HTML: {str(e)}"
