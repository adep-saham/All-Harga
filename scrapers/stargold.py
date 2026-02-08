from __future__ import annotations
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests # Library pintar pengganti requests biasa

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Menggunakan curl_cffi untuk meniru TLS Fingerprint Chrome asli.
    Sangat ampuh melewati blokir 'Connection Reset'.
    """
    try:
        if not html:
            # Skenario 'Smarter': Menyamar sebagai Chrome 110 secara total
            response = requests.get(
                URL_STARGOLD, 
                impersonate="chrome110", # Ini kunci rahasianya
                timeout=30,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
                }
            )
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        all_data = []

        # Cari tabel dengan class 'table-sm' sesuai htlm.txt Anda
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_weight = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Identifikasi baris data emas (mengandung 'gr')
                    if "gr" in raw_weight:
                        try:
                            # 1. Bersihkan Berat (0,1 gr -> 0.1)
                            w_val = raw_weight.replace("gr", "").replace(",", ".").strip()
                            
                            # 2. Bersihkan Harga (Rp. 367.400 -> 367400)
                            # Gunakan filter angka agar tidak gagal jika format Rp berubah
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
            return pd.DataFrame(), "Data kosong atau struktur berubah."

        df = pd.DataFrame(all_data)
        # Hapus duplikat & urutkan rapi sesuai app.py
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"]).sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold (Impersonate Chrome) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Akali Blokir: {str(e)}"
