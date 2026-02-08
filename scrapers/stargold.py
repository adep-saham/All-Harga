from __future__ import annotations
from datetime import datetime
import pandas as pd
import cloudscraper # Ganti requests dengan cloudscraper
from bs4 import BeautifulSoup

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Scraper menggunakan cloudscraper untuk menembus proteksi koneksi
    dan parsing presisi berdasarkan file htlm.txt.
    """
    try:
        if not html:
            # Membuat instance scraper yang meniru browser asli
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                }
            )
            response = scraper.get(URL_STARGOLD, timeout=30)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        all_data = []

        # Mencari tabel dengan class table-sm sesuai file htlm.txt
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                
                # Sesuai struktur: 0=Produk, 1=Harga Jual, 2=Harga Buyback
                if len(cols) >= 3:
                    raw_weight = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Filter: Hanya ambil baris yang mengandung 'gr' di kolom berat
                    if 'gr' in raw_weight:
                        try:
                            # Bersihkan berat: '0,1 gr' -> 0.1
                            weight_val = raw_weight.replace("gr", "").replace(",", ".").strip()
                            weight = float(weight_val)

                            # Bersihkan harga: 'Rp. 367.400' -> 367400
                            sell = int("".join(filter(str.isdigit, raw_sell)))
                            buyback = int("".join(filter(str.isdigit, raw_buyback)))

                            all_data.append({
                                "vendor": "STARGOLD",
                                "weight_g": weight,
                                "sell_idr": sell,
                                "buyback_idr": buyback
                            })
                        except (ValueError, IndexError):
                            continue

        if not all_data:
            return pd.DataFrame(), "Data tidak ditemukan. Struktur web mungkin berubah."

        # Convert ke DataFrame dan hapus duplikat
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"], keep="first")
        df = df.sort_values("weight_g").reset_index(drop=True)

        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        update_label = f"StarGold (Live Web) - Updated: {ts}"

        return df, update_label

    except Exception as e:
        return pd.DataFrame(), f"Gagal Tarik Data: {str(e)}"
