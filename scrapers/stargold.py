from __future__ import annotations
from datetime import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup

# URL Website Utama untuk scraping
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Scraper langsung dari website stargold.id/price/
    """
    try:
        # Jika dipanggil dari app.py dengan string kosong, kita ambil HTML-nya sendiri
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(URL_STARGOLD, headers=headers, timeout=20)
        response.raise_for_status()
        html_content = response.text

        soup = BeautifulSoup(html_content, "html.parser")
        
        # Mencari tabel di halaman tersebut
        tables = soup.find_all("table")
        if not tables:
            return pd.DataFrame(), "Gagal menemukan tabel harga di website."

        all_data = []
        
        # Iterasi melalui tabel (Stargold biasanya punya tabel per kategori)
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:  # Lewati header
                cols = row.find_all("td")
                if len(cols) >= 3:
                    # Ambil teks dan bersihkan
                    raw_weight = cols[0].get_text(strip=True).lower().replace("gr", "").replace(",", ".")
                    raw_sell = cols[1].get_text(strip=True).replace("Rp", "").replace(".", "").replace(",", "")
                    raw_buyback = cols[2].get_text(strip=True).replace("Rp", "").replace(".", "").replace(",", "")
                    
                    try:
                        # Konversi ke tipe data yang sesuai untuk app.py
                        weight = float(raw_weight)
                        sell = int(raw_sell) if raw_sell.isdigit() else 0
                        buyback = int(raw_buyback) if raw_buyback.isdigit() else 0
                        
                        if weight > 0:
                            all_data.append({
                                "vendor": "STARGOLD",
                                "weight_g": weight,
                                "sell_idr": sell,
                                "buyback_idr": buyback
                            })
                    except ValueError:
                        continue

        if not all_data:
            return pd.DataFrame(), "Data tidak ditemukan atau struktur tabel berubah."

        df = pd.DataFrame(all_data)
        
        # Bersihkan duplikat dan urutkan berdasarkan berat
        df = df.drop_duplicates(subset=["weight_g"], keep="first")
        df = df.sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        update_label = f"StarGold (Live Web) - Updated: {ts}"
        
        return df, update_label

    except Exception as e:
        return pd.DataFrame(), f"Error Scraping StarGold: {str(e)}"
