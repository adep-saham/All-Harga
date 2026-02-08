from __future__ import annotations
from datetime import datetime
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup

# URL Website Utama
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Scraper presisi untuk stargold.id menggunakan cloudscraper.
    """
    try:
        # 1. Ambil HTML jika tidak diberikan (Live Scraping)
        if not html:
            # Cloudscraper meniru browser asli untuk menghindari 'Connection Reset'
            scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
            )
            response = scraper.get(URL_STARGOLD, timeout=20)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        all_data = []

        # 2. Cari tabel dengan class 'table-sm' sesuai htlm.txt
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                
                # Sesuai htlm.txt: Kolom 0=Berat, 1=Jual, 2=Buyback
                if len(cols) >= 3:
                    raw_weight = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Filter: Hanya ambil baris yang mengandung satuan berat 'gr'
                    if "gr" in raw_weight:
                        try:
                            # Bersihkan Berat: '0,1 gr' -> 0.1 (Ganti koma jadi titik)
                            weight_val = raw_weight.replace("gr", "").replace(",", ".").strip()
                            
                            # Bersihkan Harga: 'Rp. 367.400' -> 367400 (Ambil angka saja)
                            sell_val = "".join(filter(str.isdigit, raw_sell))
                            buyback_val = "".join(filter(str.isdigit, raw_buyback))

                            all_data.append({
                                "vendor": "STARGOLD",
                                "weight_g": float(weight_val),
                                "sell_idr": int(sell_val) if sell_val else 0,
                                "buyback_idr": int(buyback_val) if buyback_val else 0
                            })
                        except (ValueError, IndexError):
                            continue

        if not all_data:
            return pd.DataFrame(), "Gagal mengekstrak data dari tabel HTML."

        # 3. Finalisasi Data
        df = pd.DataFrame(all_data)
        # Hapus duplikat dan urutkan berdasarkan berat
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"]).sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        update_label = f"StarGold (Live Scrape) - Updated: {ts}"
        
        return df, update_label

    except Exception as e:
        return pd.DataFrame(), f"Error Scraping: {str(e)}"
