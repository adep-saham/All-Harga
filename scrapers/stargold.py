from __future__ import annotations
import os
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Jalur Stealth v2:
    1. Menggunakan profil Chrome yang paling kompatibel.
    2. Pencarian file htlm.txt yang lebih cerdas (mencari di folder utama).
    3. Parsing presisi untuk harga emas Stargold, Antam, dan UBS.
    """
    final_html = html
    source_label = "Live Web"

    # --- 1. JALUR UDARA (FETCHING) ---
    if not final_html:
        try:
            # Gunakan chrome110, ini paling stabil di curl_cffi
            response = requests.get(
                URL_STARGOLD,
                impersonate="chrome110", 
                timeout=20,
                headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8",
                    "referer": "https://www.google.com/"
                }
            )
            response.raise_for_status()
            final_html = response.text
        except Exception:
            # --- JALUR DARAT (FALLBACK HTLM.TXT) ---
            # Cari htlm.txt di folder saat ini dan folder induk (root project)
            possible_paths = [
                "htlm.txt",
                os.path.join(os.getcwd(), "htlm.txt"),
                os.path.join(os.path.dirname(os.getcwd()), "htlm.txt"),
                "scrapers/htlm.txt"
            ]
            
            found = False
            for path in possible_paths:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        final_html = f.read()
                    source_label = "Offline (htlm.txt)"
                    found = True
                    break
            
            if not found:
                return pd.DataFrame(), "Gagal: Server blokir & htlm.txt tidak ditemukan di root folder."

    # --- 2. PROSES PARSING (EKSTRAKSI DATA) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Cari tabel dengan class table-sm (struktur dasar Stargold)
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                
                # Sesuai file htlm.txt: [0] Berat/Produk, [1] Jual, [2] Buyback
                if len(cols) >= 3:
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Filter baris yang mengandung satuan 'gr'
                    if "gr" in raw_name:
                        try:
                            # Identifikasi Vendor
                            vendor = "STARGOLD"
                            if "antam" in raw_name: vendor = "ANTAM"
                            elif "ubs" in raw_name: vendor = "UBS"

                            # Bersihkan Berat (0,1 gr -> 0.1)
                            # Ambil angka desimal terakhir dari string berat
                            w_str = raw_name.replace("gr", "").replace(",", ".").strip()
                            w_val = float(w_str.split()[-1])

                            # Bersihkan Harga (Hanya ambil angka)
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
            return pd.DataFrame(), f"Data kosong di {source_label}. Cek isi HTML."

        # Finalisasi DataFrame
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
