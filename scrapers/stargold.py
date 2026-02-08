from __future__ import annotations
from datetime import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Scraper dengan header yang lebih kuat untuk menghindari blokir server.
    """
    try:
        # Gunakan Session untuk menjaga konteks koneksi
        session = requests.Session()
        
        # Header lebih lengkap meniru Chrome di Windows
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

        # Melakukan request langsung ke URL
        response = session.get(URL_STARGOLD, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Mencari semua tabel di halaman
        tables = soup.find_all("table")
        if not tables:
            return pd.DataFrame(), "Gagal menemukan tabel harga di halaman."

        all_data = []
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:  # Lewati header tabel
                cols = row.find_all("td")
                if len(cols) >= 3:
                    # Ambil teks dan bersihkan karakter non-numerik
                    text_weight = cols[0].get_text(strip=True).lower().replace("gr", "").replace(",", ".")
                    text_sell = cols[1].get_text(strip=True).replace("Rp", "").replace(".", "").replace(",", "")
                    text_buyback = cols[2].get_text(strip=True).replace("Rp", "").replace(".", "").replace(",", "")
                    
                    try:
                        # Parsing ke tipe data numerik
                        weight = float(text_weight)
                        sell = int(text_sell) if text_sell.isdigit() else 0
                        buyback = int(text_buyback) if text_buyback.isdigit() else 0
                        
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
            return pd.DataFrame(), "Data ditemukan tapi gagal diproses (struktur mungkin berubah)."

        df = pd.DataFrame(all_data)
        
        # Hilangkan duplikat jika ada tabel yang overlap
        df = df.drop_duplicates(subset=["weight_g"], keep="first")
        df = df.sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        update_label = f"StarGold (Live Web) - Updated: {ts}"
        
        return df, update_label

    except requests.exceptions.RequestException as e:
        return pd.DataFrame(), f"Koneksi Ditolak: {str(e)}"
    except Exception as e:
        return pd.DataFrame(), f"Error Fatal: {str(e)}"
