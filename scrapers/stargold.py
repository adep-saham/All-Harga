from __future__ import annotations
from datetime import datetime
import pandas as pd
import cloudscraper  # Library ini wajib ada
from bs4 import BeautifulSoup

# URL Website Utama
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Scraper khusus untuk menembus proteksi Stargold dan membaca htlm.txt Anda.
    """
    try:
        # 1. Ambil data secara mandiri menggunakan cloudscraper
        if not html:
            # Membuat session yang meniru Chrome di Windows
            scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
            )
            # Menembus proteksi yang bikin error 'RemoteDisconnected'
            response = scraper.get(URL_STARGOLD, timeout=30)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        all_data = []

        # 2. Cari tabel dengan class 'table-sm' (sesuai file htlm.txt Anda)
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                
                # Struktur: [0] Berat, [1] Jual, [2] Buyback
                if len(cols) >= 3:
                    raw_weight = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Pastikan ini baris data (mengandung 'gr')
                    if "gr" in raw_weight:
                        try:
                            # Bersihkan Berat: '0,1 gr' -> 0.1
                            w_val = raw_weight.replace("gr", "").replace(",", ".").strip()
                            # Bersihkan Harga: Ambil angka saja (membuang Rp dan titik ribuan)
                            s_val = "".join(filter(str.isdigit, raw_sell))
                            b_val = "".join(filter(str.isdigit, raw_buyback))

                            all_data.append({
                                "vendor": "STARGOLD",
                                "weight_g": float(w_val),
                                "sell_idr": int(s_val) if s_val else 0,
                                "buyback_idr": int(b_val) if b_val else 0
                            })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), "Gagal ekstrak tabel (Struktur HTML berubah)"

        df = pd.DataFrame(all_data)
        # Hilangkan duplikat dan urutkan
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"]).sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold (Live) - {ts}"

    except Exception as e:
        # Jika error di sini, kemungkinan cloudscraper belum terinstall
        return pd.DataFrame(), f"Error Scraping: {str(e)}"
