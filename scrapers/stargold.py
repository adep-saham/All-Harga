from __future__ import annotations
from datetime import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup

# URL Website Utama
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Melakukan scraping langsung dari tabel di https://stargold.id/price/
    """
    try:
        # Jika html kosong (dipanggil tanpa argumen), ambil data baru
        if not html:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(URL_STARGOLD, headers=headers, timeout=30)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        
        # Cari tabel di halaman tersebut
        # Biasanya data harga ada di dalam tag <table>
        tables = soup.find_all("table")
        
        all_data = []
        
        for table in tables:
            # Identifikasi baris tabel
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header
                cols = row.find_all("td")
                if len(cols) >= 3:
                    # Bersihkan teks (hapus "gr", "Rp", titik, dan spasi)
                    weight_text = cols[0].text.strip().lower().replace("gr", "").replace(",", ".")
                    sell_text = cols[1].text.strip().replace("Rp", "").replace(".", "").replace(",", "")
                    buyback_text = cols[2].text.strip().replace("Rp", "").replace(".", "").replace(",", "")
                    
                    try:
                        all_data.append({
                            "vendor": "STARGOLD",
                            "weight_g": float(weight_text),
                            "sell_idr": int(sell_text) if sell_text.isdigit() else 0,
                            "buyback_idr": int(buyback_text) if buyback_text.isdigit() else 0
                        })
                    except ValueError:
                        continue

        if not all_data:
            return pd.DataFrame(), "Data tidak ditemukan di tabel website."

        df = pd.DataFrame(all_data)
        
        # Standarisasi data
        df = df.sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        update_label = f"StarGold (Live Web) - Updated: {ts}"
        
        return df, update_label

    except Exception as e:
        return pd.DataFrame(), f"Error Scraping: {str(e)}"
