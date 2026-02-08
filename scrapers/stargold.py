from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Jalur Stealth Hacker:
    1. Mencoba bypass firewall menggunakan HTTP/1.1 (lebih sulit dideteksi bot modern).
    2. Jika koneksi diputus, otomatis mendeteksi file 'htlm.txt' di folder project.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. JALUR UDARA (LIVE FETCH) ---
    if not final_html or len(final_html) < 100:
        try:
            # Gunakan session dan paksa protokol HTTP/1.1 agar sidik jari TLS lebih natural
            with requests.Session() as s:
                response = s.get(
                    URL_STARGOLD,
                    impersonate="chrome110",
                    http_version=1, # Kunci utama: Paksa HTTP/1.1
                    timeout=20,
                    headers={
                        "authority": "stargold.id",
                        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "accept-language": "id-ID,id;q=0.9,en-US;q=0.8",
                        "referer": "https://www.google.com/",
                        "sec-ch-ua-platform": '"Windows"',
                    }
                )
                response.raise_for_status()
                final_html = response.text
        except Exception:
            # --- 2. JALUR DARAT (AUTO-RADAR HTLM.TXT) ---
            # Mencari file htlm.txt di folder utama atau folder scrapers
            current_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(current_dir)
            
            paths = [
                os.path.join(root_dir, "htlm.txt"),
                os.path.join(current_dir, "htlm.txt"),
                "htlm.txt"
            ]
            
            found = False
            for p in paths:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        final_html = f.read()
                    source_label = "Offline (htlm.txt)"
                    found = True
                    break
            
            if not found:
                return pd.DataFrame(), "Semua jalur buntu: Koneksi ditolak & htlm.txt tidak ditemukan."

    # --- 3. EKSTRAKSI DATA (PARSER) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Target tabel berdasarkan file htlm.txt Anda
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    # Ambil teks produk (contoh: "Stargold 0,5 gr" atau "Antam 1 gr")
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    if "gr" in raw_name:
                        try:
                            # Tentukan Vendor (Smarter Detection)
                            vendor = "STARGOLD"
                            if "antam" in raw_name: vendor = "ANTAM"
                            elif "ubs" in raw_name: vendor = "UBS"

                            # Bersihkan Berat: "0,5 gr" -> 0.5
                            # Ganti koma jadi titik untuk standar Python
                            w_str = raw_name.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka paling belakang (menangani nama vendor di depan berat)
                            w_val = float(w_str.split()[-1])

                            # Bersihkan Harga: Ambil digit saja
                            sell_val = "".join(filter(str.isdigit, raw_sell))
                            buyback_val = "".join(filter(str.isdigit, raw_buyback))

                            if sell_val:
                                all_data.append({
                                    "vendor": vendor,
                                    "weight_g": w_val,
                                    "sell_idr": int(sell_val),
                                    "buyback_idr": int(buyback_val) if buyback_val else 0
                                })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), f"Gagal urai data. Pastikan htlm.txt berisi tabel harga."

        df = pd.DataFrame(all_data)
        # Hapus duplikat dan urutkan sesuai standar app.py
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%H:%M:%S")
        return df, f"StarGold {source_label} - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Error Parser: {str(e)}"
