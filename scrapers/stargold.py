from __future__ import annotations
import os
import json
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Jalur Stealth Hacker:
    1. Menggunakan Public Proxy API (AllOrigins) untuk bypass Geoblocking.
    2. Menyamar sebagai iPhone (Mobile Safari) agar tidak dicurigai bot server.
    3. Fallback ke htlm.txt jika jalur udara terdeteksi.
    """
    final_html = html
    source_label = "Live Proxy"

    if not final_html:
        try:
            # Trik Hacker: Gunakan AllOrigins Proxy untuk mengambil konten web.
            # Ini akan membuat request seolah-olah datang dari server proxy, bukan server Anda.
            proxy_url = f"https://api.allorigins.win/get?url={URL_STARGOLD}"
            
            response = requests.get(
                proxy_url,
                impersonate="safari_ios_16_0", # Menyamar jadi iPhone agar lebih aman
                timeout=30
            )
            
            if response.status_code == 200:
                # AllOrigins membungkus HTML dalam format JSON {'contents': '<html>...'}
                data_json = response.json()
                final_html = data_json.get("contents", "")
            
            if not final_html or len(final_html) < 500:
                raise Exception("Proxy returned empty or blocked content")

        except Exception as e:
            # Jika jalur Proxy gagal, cari file 'htlm.txt' di folder yang sama dengan app.py
            # Saya tambahkan pengecekan path agar lebih akurat
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            
            # Cari di folder utama atau folder scrapers
            paths_to_check = [
                os.path.join(parent_dir, "htlm.txt"),
                os.path.join(current_dir, "htlm.txt"),
                "htlm.txt"
            ]
            
            found = False
            for p in paths_to_check:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        final_html = f.read()
                    source_label = "Fallback (htlm.txt)"
                    found = True
                    break
            
            if not found:
                return pd.DataFrame(), f"Semua jalur buntu: {str(e)}"

    # --- PROSES PARSING (Logika Ekstraksi Data) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Target: Tabel dengan class table-sm
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
                            # Bersihkan Berat (0,1 gr -> 0.1)
                            weight_str = raw_name.replace("gr", "").replace(",", ".").strip()
                            weight_val = float(weight_str.split()[-1])

                            # Bersihkan Harga
                            s_val = "".join(filter(str.isdigit, raw_sell))
                            b_val = "".join(filter(str.isdigit, raw_buyback))

                            if s_val:
                                all_data.append({
                                    "vendor": "STARGOLD",
                                    "weight_g": weight_val,
                                    "sell_idr": int(s_val),
                                    "buyback_idr": int(b_val) if b_val else 0
                                })
                        except: continue

        if not all_data:
            return pd.DataFrame(), f"Data tidak ditemukan di {source_label}. Cek format HTML."

        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"]).sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Error di Parser: {str(e)}"
