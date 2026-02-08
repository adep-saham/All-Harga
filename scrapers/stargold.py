from __future__ import annotations
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests # Wajib: pip install curl_cffi

URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Versi 'Stealth Ultimate': Meniru Browser secara identik di level TLS dan Header.
    """
    try:
        if not html:
            # Gunakan Session untuk menjaga state koneksi
            with requests.Session() as s:
                response = s.get(
                    URL_STARGOLD,
                    impersonate="chrome110", # Meniru sidik jari Chrome
                    timeout=30,
                    headers={
                        "authority": "stargold.id",
                        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
                        "cache-control": "max-age=0",
                        "referer": "https://www.google.com/", # Pura-pura datang dari Google
                        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="110", "Chromium";v="110"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                        "sec-fetch-dest": "document",
                        "sec-fetch-mode": "navigate",
                        "sec-fetch-site": "cross-site",
                        "sec-fetch-user": "?1",
                        "upgrade-insecure-requests": "1",
                        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                    }
                )
                response.raise_for_status()
                html = response.text

        soup = BeautifulSoup(html, "html.parser")
        all_data = []

        # Ambil tabel harga (Berdasarkan file htlm.txt Anda)
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_weight = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    if "gr" in raw_weight:
                        try:
                            # Parsing desimal Indo (koma jadi titik)
                            w_val = raw_weight.replace("gr", "").replace(",", ".").strip()
                            s_val = "".join(filter(str.isdigit, raw_sell))
                            b_val = "".join(filter(str.isdigit, raw_buyback))

                            if s_val:
                                all_data.append({
                                    "vendor": "STARGOLD",
                                    "weight_g": float(w_val),
                                    "sell_idr": int(s_val),
                                    "buyback_idr": int(b_val) if b_val else 0
                                })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), "Data kosong (Server mungkin memblokir konten)."

        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"]).sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold (Success) - {ts}"

    except Exception as e:
        # Jika benar-benar buntu, kita bisa tambahkan opsi manual
        return pd.DataFrame(), f"Gagal tembus firewall: {str(e)}"
