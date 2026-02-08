from __future__ import annotations
import os
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests # Wajib: pip install curl_cffi

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Versi Perbaikan: Menggunakan nilai integer untuk versi HTTP agar kompatibel 
    dengan semua versi curl_cffi dan tetap menembus blokir firewall.
    """
    final_html = html
    source_info = "Live Web"

    if not final_html:
        try:
            # Menggunakan impersonate chrome110 untuk meniru sidik jari browser
            # Nilai 1 pada http_version memaksa penggunaan protokol HTTP/1.1
            response = requests.get(
                URL_STARGOLD,
                impersonate="chrome110",
                http_version=1, 
                timeout=30,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
                    "Referer": "https://www.google.com/",
                    "Cache-Control": "no-cache"
                }
            )
            response.raise_for_status()
            final_html = response.text
        except Exception as e:
            # Jika tetap gagal karena IP diblokir, gunakan fallback ke file lokal
            if os.path.exists("htlm.txt"):
                with open("htlm.txt", "r", encoding="utf-8") as f:
                    final_html = f.read()
                source_info = "Manual (htlm.txt)"
            else:
                return pd.DataFrame(), f"Blokir Server: {str(e)}"

    # PROSES PARSING DATA (Disesuaikan dengan file htlm.txt Anda)
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []
        
        # Mencari tabel dengan class table-sm yang berisi data harga
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Filter hanya baris yang mengandung satuan berat 'gr'
                    if "gr" in raw_name:
                        try:
                            # Bersihkan berat: '0,1 gr' -> 0.1
                            w_val = raw_name.replace("gr", "").replace(",", ".").strip()
                            # Ambil bagian angka jika ada teks merek di depan berat
                            w_val = w_val.split()[-1] 

                            # Ambil angka saja untuk harga (menghapus Rp dan titik ribuan)
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
            return pd.DataFrame(), f"Data kosong di {source_info}. Cek isi HTML."

        # Membuat DataFrame dan mengurutkan berdasarkan berat
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"]).sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_info}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai Data: {str(e)}"
