from __future__ import annotations
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup

def parse_stargold(html: str) -> tuple[pd.DataFrame, str]:
    """
    Parser tangguh yang fokus membedah HTML dari htlm.txt.
    Tidak melakukan fetch di sini agar tidak memicu Connection Reset.
    """
    if not html or len(html) < 100:
        return pd.DataFrame(), "Pemicu: HTML kosong. Gunakan fitur tempel manual."

    try:
        soup = BeautifulSoup(html, "html.parser")
        all_data = []

        # Mencari semua tabel harga (class table-sm di htlm.txt)
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Pastikan baris mengandung satuan berat 'gr'
                    if "gr" in raw_name:
                        try:
                            # 1. Bersihkan Nama/Vendor (Cek apakah Antam/UBS/Stargold)
                            vendor = "STARGOLD"
                            if "antam" in raw_name: vendor = "ANTAM"
                            elif "ubs" in raw_name: vendor = "UBS"
                            
                            # 2. Parsing Berat (0,1 gr -> 0.1)
                            weight_val = raw_name.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka paling akhir jika ada nama vendor di depan
                            weight_val = weight_val.split()[-1] 

                            # 3. Bersihkan Harga (Rp. 367.400 -> 367400)
                            s_val = "".join(filter(str.isdigit, raw_sell))
                            b_val = "".join(filter(str.isdigit, raw_buyback))

                            if s_val:
                                all_data.append({
                                    "vendor": vendor,
                                    "weight_g": float(weight_val),
                                    "sell_idr": int(s_val),
                                    "buyback_idr": int(b_val) if b_val else 0
                                })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), "Gagal ekstrak data. Pastikan Anda menyalin seluruh isi halaman (Ctrl+A -> Ctrl+C)."

        df = pd.DataFrame(all_data)
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"Berhasil diurai dari HTML - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal urai HTML: {str(e)}"
