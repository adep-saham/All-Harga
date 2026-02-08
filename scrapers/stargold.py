from __future__ import annotations
import os
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests # Wajib: pip install curl_cffi

# URL Tetap sesuai app.py
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Fungsi ini tetap menerima parameter 'html' agar app.py tidak perlu diubah.
    Logika:
    1. Coba ambil data live dengan curl_cffi (Impersonate Chrome).
    2. Jika gagal (Connection Reset), otomatis cari file 'htlm.txt' sebagai cadangan.
    """
    final_html = html
    source_info = "Live Web"

    # 1. LOGIKA AMBIL DATA (Jika html dari app.py kosong)
    if not final_html:
        try:
            # Menggunakan impersonate chrome110 untuk meniru TLS Fingerprint asli
            # Memaksa HTTP/1.1 untuk menghindari deteksi HTTP/2 bot
            response = requests.get(
                URL_STARGOLD,
                impersonate="chrome110",
                timeout=30,
                headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8",
                    "referer": "https://www.google.com/",
                    "upgrade-insecure-requests": "1"
                }
            )
            response.raise_for_status()
            final_html = response.text
        except Exception as e:
            # FALLBACK CERDAS: Jika koneksi diputus, cek apakah ada file htlm.txt di folder
            if os.path.exists("htlm.txt"):
                with open("htlm.txt", "r", encoding="utf-8") as f:
                    final_html = f.read()
                source_info = "Local File (htlm.txt)"
            else:
                return pd.DataFrame(), f"Blokir Server: {str(e)}. (Tips: Simpan source web ke htlm.txt)"

    # 2. LOGIKA PARSING (Sesuai struktur htlm.txt Anda)
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []
        
        # Cari tabel dengan class table-sm sesuai htlm.txt
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_weight = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    if "gr" in raw_weight:
                        try:
                            # Bersihkan Berat (0,1 gr -> 0.1)
                            w_val = raw_weight.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka harga saja (Rp. 367.400 -> 367400)
                            s_val = "".join(filter(str.isdigit, raw_sell))
                            b_val = "".join(filter(str.isdigit, raw_buyback))

                            if s_val:
                                all_data.append({
                                    "vendor": "STARGOLD",
                                    "weight_g": float(w_val),
                                    "sell_idr": int(s_val),
                                    "buyback_idr": int(b_val) if b_val else 0
                                })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), f"Data tidak ditemukan di {source_info}."

        # Sinkronisasi dengan ekspektasi app.py
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"]).sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_info}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Error Parsing: {str(e)}"
