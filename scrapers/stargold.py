from __future__ import annotations
import os
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

# URL Target
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Strategi Smart Fallback: 
    1. Mencoba koneksi live dengan sidik jari browser asli.
    2. Jika kena 'Connection Reset', otomatis membaca dari file 'htlm.txt'.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. PROSES PENGAMBILAN DATA ---
    if not final_html:
        try:
            # Menggunakan impersonate chrome110 (Sidik jari Chrome asli)
            response = requests.get(
                URL_STARGOLD,
                impersonate="chrome110",
                timeout=15,
                headers={
                    "referer": "https://www.google.com/",
                    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8",
                }
            )
            response.raise_for_status()
            final_html = response.text
        except Exception:
            # Jika LIVE gagal (karena diblokir), cari file htlm.txt di folder yang sama
            if os.path.exists("htlm.txt"):
                with open("htlm.txt", "r", encoding="utf-8") as f:
                    final_html = f.read()
                source_label = "Local File (htlm.txt)"
            else:
                return pd.DataFrame(), "Gagal: Server memblokir koneksi & htlm.txt tidak ditemukan."

    # --- 2. PROSES PARSING (Sesuai file htlm.txt Anda) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Mencari tabel dengan class 'table-sm'
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                
                # Struktur: [0] Produk/Berat, [1] Harga Jual, [2] Buyback
                if len(cols) >= 3:
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Filter baris yang berisi berat (contoh: '0,1 gr')
                    if "gr" in raw_name:
                        try:
                            # Bersihkan Berat: '0,1 gr' -> 0.1
                            weight_str = raw_name.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka di posisi terakhir (jika ada nama brand)
                            weight_val = float(weight_str.split()[-1])

                            # Bersihkan Harga: Ambil angka saja
                            sell_val = int("".join(filter(str.isdigit, raw_sell)))
                            buyback_val = int("".join(filter(str.isdigit, raw_buyback)))

                            all_data.append({
                                "vendor": "STARGOLD",
                                "weight_g": weight_val,
                                "sell_idr": sell_val,
                                "buyback_idr": buyback_val
                            })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), f"Gagal urai data dari {source_label}."

        # Finalisasi DataFrame sesuai kebutuhan app.py
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"])
        df = df.sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Error pada Parser: {str(e)}"
