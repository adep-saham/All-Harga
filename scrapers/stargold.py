from __future__ import annotations
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
import requests

# URL Target
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Scraper yang disesuaikan dengan struktur HTML asli stargold.id
    """
    try:
        # 1. Ambil HTML jika tidak disediakan
        if not html:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Referer": "https://stargold.id/",
            }
            # Menggunakan timeout lebih lama untuk menghindari pemutusan koneksi sepihak
            response = requests.get(URL_STARGOLD, headers=headers, timeout=30)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        all_data = []

        # 2. Cari tabel berdasarkan class yang ada di file htlm.txt Anda
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                
                # Berdasarkan file Anda: td[0]=Berat, td[1]=Harga Jual, td[2]=Buyback
                if len(cols) >= 3:
                    raw_weight = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Lewati baris header jika terbawa (misal kata "Harga")
                    if "harga" in raw_sell.lower() or "produk" in raw_weight:
                        continue

                    try:
                        # Cleaning Data
                        # Menghapus 'gr', '.', dan 'Rp'
                        weight = float(raw_weight.replace("gr", "").replace(",", ".").strip())
                        sell = int("".join(filter(str.isdigit, raw_sell)))
                        buyback = int("".join(filter(str.isdigit, raw_buyback)))

                        if weight > 0:
                            all_data.append({
                                "vendor": "STARGOLD",
                                "weight_g": weight,
                                "sell_idr": sell,
                                "buyback_idr": buyback
                            })
                    except (ValueError, IndexError):
                        continue

        if not all_data:
            return pd.DataFrame(), "Data tidak ditemukan (Cek struktur tabel)"

        # 3. Finalisasi DataFrame
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"], keep="first")
        df = df.sort_values("weight_g").reset_index(drop=True)

        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        update_label = f"StarGold (Live Web) - Updated: {ts}"

        return df, update_label

    except Exception as e:
        return pd.DataFrame(), f"Error Scraping: {str(e)}"
