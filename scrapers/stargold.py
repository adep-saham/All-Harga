from __future__ import annotations
import os
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests # Wajib: pip install curl_cffi

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Versi Anti-Blokir HTTP/2: Memaksa protokol HTTP/1.1 untuk menghindari stream cancel.
    """
    final_html = html
    source_info = "Live Web"

    if not final_html:
        try:
            # Menggunakan curl_cffi untuk meniru Chrome 110
            # KUNCI: Menambahkan http_version=requests.HttpVersion.v1_1
            response = requests.get(
                URL_STARGOLD,
                impersonate="chrome110",
                http_version=requests.HttpVersion.v1_1, # Memaksa HTTP/1.1
                timeout=30,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
                    "Referer": "https://www.google.com/",
                    "Cache-Control": "no-cache"
                }
            )
            response.raise_for_status()
            final_html = response.text
        except Exception as e:
            # Jika tetap gagal, gunakan file htlm.txt yang Anda buat
            if os.path.exists("htlm.txt"):
                with open("htlm.txt", "r", encoding="utf-8") as f:
                    final_html = f.read()
                source_info = "Manual (htlm.txt)"
            else:
                return pd.DataFrame(), f"Blokir Protokol: {str(e)}"

    # PROSES PARSING (Sesuai htlm.txt)
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []
        
        # Cari tabel (class table-sm di htlm.txt)
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    if "gr" in raw_name:
                        try:
                            # Bersihkan Berat (Indo: 0,1 gr -> 0.1)
                            w_val = raw_name.replace("gr", "").replace(",", ".").strip()
                            w_val = w_val.split()[-1] # Ambil angka terakhir jika ada nama merek

                            # Bersihkan Harga
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
            return pd.DataFrame(), "Data tidak ditemukan. Pastikan isi htlm.txt lengkap."

        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"]).sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_info}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Error Parse: {str(e)}"
