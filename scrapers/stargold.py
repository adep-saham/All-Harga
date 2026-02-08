from __future__ import annotations
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# URL Sasaran
URL_STARGOLD = "https://stargold.id/price/"

def parse_stargold(html: str = "") -> tuple[pd.DataFrame, str]:
    """
    Scraper Versi 'Browser Simulation' (Playwright):
    1. Meniru manusia membuka browser untuk melepasi firewall.
    2. Jika gagal, automatik membaca file 'source web.txt' sebagai sandaran.
    """
    final_html = html
    source_label = "Live Browser"

    # --- TAHAP 1: PENGAMBILAN DATA (LIVE BROWSER) ---
    if not final_html or len(final_html) < 500:
        try:
            with sync_playwright() as p:
                # Membuka pelayar tanpa tetingkap (headless)
                browser = p.chromium.launch(headless=True)
                # Meniru identiti Chrome/Windows yang asli
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                
                # Pergi ke URL dan tunggu sehingga rangkaian stabil (network idle)
                page.goto(URL_STARGOLD, wait_until="networkidle", timeout=60000)
                
                # Mengambil kod sumber (View Source) secara automatik
                final_html = page.content()
                browser.close()
        except Exception as e:
            # --- TAHAP 2: JALUR SANDARAN (FILE TXT) ---
            # Jika browser gagal (blokir IP), cari file manual anda
            current_dir = os.getcwd()
            target_files = ["source web.txt", "htlm.txt"]
            
            found_path = None
            for f_name in target_files:
                p_path = os.path.join(current_dir, f_name)
                if os.path.exists(p_path):
                    found_path = p_path
                    break
            
            if found_path:
                with open(found_path, "r", encoding="utf-8") as f:
                    final_html = f.read()
                source_label = f"Offline ({os.path.basename(found_path)})"
            else:
                return pd.DataFrame(), f"Gagal: Browser disekat & file TXT tidak dijumpai."

    # --- TAHAP 3: EKSTRAKSI DATA (BEAUTIFULSOUP) ---
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        all_data = []

        # Mencari tabel dengan class table-sm (seperti dalam source web.txt anda)
        tables = soup.find_all("table", class_="table-sm")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_name = cols[0].get_text(strip=True).lower()
                    raw_sell = cols[1].get_text(strip=True)
                    raw_buyback = cols[2].get_text(strip=True)

                    # Hanya proses baris yang mengandungi berat 'gr'
                    if "gr" in raw_name:
                        try:
                            # Tentukan Vendor (Antam/UBS/Stargold)
                            vendor = "STARGOLD"
                            if "antam" in raw_name: vendor = "ANTAM"
                            elif "ubs" in raw_name: vendor = "UBS"

                            # Bersihkan Berat: '0,5 gr' -> 0.5
                            w_str = raw_name.replace("gr", "").replace(",", ".").strip()
                            w_val = float(w_str.split()[-1])

                            # Bersihkan Harga: Ambil angka sahaja
                            s_val = "".join(filter(str.isdigit, raw_sell))
                            b_val = "".join(filter(str.isdigit, raw_buyback))

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
            return pd.DataFrame(), f"Data kosong di {source_label}. Sila semak kandungan HTML."

        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr"])
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)
        
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return df, f"StarGold ({source_label}) - {ts}"

    except Exception as e:
        return pd.DataFrame(), f"Gagal Urai: {str(e)}"
