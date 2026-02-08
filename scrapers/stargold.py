from __future__ import annotations
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests # Wajib: pip install curl_cffi

URL_BASE = "https://stargold.id/"
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Teknik Stealth: Menggunakan Session untuk simulasi kunjungan bertahap
    dan memaksa protokol HTTP/1.1 agar sidik jari TLS lebih stabil.
    """
    try:
        if not html:
            # Gunakan Session untuk menyimpan cookies
            with requests.Session() as s:
                # 1. TAHAP PERTAMA: Kunjungi Home Page (Membangun Kepercayaan Server)
                # Gunakan impersonate chrome110 untuk sidik jari browser
                s.get(URL_BASE, impersonate="chrome110", timeout=20)
                
                # 2. TAHAP KEDUA: Kunjungi Halaman Harga
                response = s.get(
                    URL_STARGOLD,
                    impersonate="chrome110",
                    timeout=30,
                    # Memaksa HTTP/1.1 karena seringkali HTTP/2 bot terdeteksi berbeda
                    allow_redirects=True,
                    headers={
                        "Referer": URL_BASE,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
                        "Upgrade-Insecure-Requests": "1"
                    }
                )
                response.raise_for_status()
                html = response.text

        soup = BeautifulSoup(html, "html.parser")
        all_data = []

        # Cari tabel (Sesuai file htlm.txt Anda)
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
                            # Bersihkan Berat (Indo format: 0,1 gr)
                            w_val = raw_weight.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka harga saja
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
            return pd.DataFrame(), "Server berhasil ditembus, tapi data tabel kosong."

        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["weight_g", "sell_idr"]).sort_values("weight_g").reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold (Stealth Mode) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Blokir Firewall Terdeteksi: {str(e)}"
