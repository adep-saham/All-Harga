from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Parser 'Hacker Baik': Fokus 100% pada pembacaan fail 'source web.txt'
    yang anda muat naik ke GitHub.
    """
    final_html = html
    source_label = "Live Web"

    # --- TAHAP 1: RADAR PENCARIAN FAIL DI STREAMLIT CLOUD ---
    if not final_html or len(final_html) < 500:
        # Laluan yang dikesan oleh ralat anda tadi
        root_path = "/mount/src/all-harga"
        target_file = "source web.txt"
        
        full_path = os.path.join(root_path, target_file)
        
        # Jika tidak jumpa di root_path, cari di folder semasa
        if not os.path.exists(full_path):
            full_path = target_file

        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                final_html = f.read()
            source_label = f"Offline ({target_file})"
        else:
            return pd.DataFrame(), f"Gagal: Sila muat naik '{target_file}' ke GitHub anda di folder utama."

    # --- TAHAP 2: EKSTRAKSI DATA DARIPADA HTML ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Berdasarkan source web.txt, data ada dalam table dengan class 'table-sm'
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                
                # Struktur: [0] Produk/Berat, [1] Harga Jual, [2] Harga Buyback
                if len(cols) >= 3:
                    name_text = cols[0].get_text(strip=True).lower()
                    sell_text = cols[1].get_text(strip=True)
                    buyback_text = cols[2].get_text(strip=True)

                    # Kita cari baris yang ada unit 'gr'
                    if "gr" in name_text:
                        try:
                            # 1. Kenal Pasti Vendor (Antam, UBS, atau Stargold)
                            vendor = "STARGOLD"
                            if "antam" in name_text: vendor = "ANTAM"
                            elif "ubs" in name_text: vendor = "UBS"
                            elif "emaskita" in name_text: vendor = "EMASKITA"

                            # 2. Bersihkan Berat: '0,5 gr' -> 0.5
                            # Tukar koma kepada titik (format sistem)
                            w_str = name_text.replace("gr", "").replace(",", ".").strip()
                            # Ambil angka sahaja (biasanya di hujung selepas nama brand)
                            w_val = float(w_str.split()[-1])

                            # 3. Bersihkan Harga: Ambil digit sahaja (buang Rp, titik, dsb)
                            s_val = "".join(filter(str.isdigit, sell_text))
                            b_val = "".join(filter(str.isdigit, buyback_text))

                            if s_val:
                                all_data.append({
                                    "vendor": vendor,
                                    "weight_g": w_val,
                                    "sell_idr": int(s_val),
                                    "buyback_idr": int(b_val) if b_val else 0
                                })
                        except:
                            continue

        if not all_data:
            return pd.DataFrame(), f"Data kosong. Sila semak kandungan fail {target_file}."

        # Tukar ke DataFrame dan susun mengikut vendor & berat
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Ralat Urai: {str(e)}"
