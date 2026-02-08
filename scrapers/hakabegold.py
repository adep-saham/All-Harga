import pandas as pd
import requests
from io import BytesIO
from typing import Tuple

# Ini adalah Link Download Resmi (Direct Stream)
# Kita tidak scraping webnya, kita langsung minta filenya ke OneDrive baik-baik.
# resid = ID File Unik
# authkey = Kunci Publik File
DIRECT_DOWNLOAD_URL = "https://onedrive.live.com/download?resid=7181A7DF3EAB3581!106&authkey=!AI3AF18"

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    """
    Mengunduh file Excel secara langsung menggunakan jalur resmi OneDrive.
    Tanpa emulasi browser, tanpa bypass bot. Murni HTTP Request standar.
    """
    try:
        # 1. Request file dengan sopan
        # User-Agent standar agar server tahu ini script python/browser umum
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = requests.get(DIRECT_DOWNLOAD_URL, headers=headers, timeout=30)
        
        # Cek apakah diizinkan (200 OK)
        if response.status_code != 200:
            return pd.DataFrame(), f"HK Logam Mulia — Server sibuk/File tidak dapat diakses (Code: {response.status_code})"

        # 2. Baca Excel
        # Kita gunakan engine openpyxl untuk membaca format .xlsx modern
        try:
            xls_data = BytesIO(response.content)
            # Baca semua sheet tanpa header dulu untuk scanning posisi tabel
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            return pd.DataFrame(), "HK Logam Mulia — Format file bukan Excel yang valid"

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # 3. Cari Data (Scanning Cerdas)
        # Kita cari di mana tabel berada, karena posisi baris bisa berubah-ubah
        for sheet_name, df in xls.items():
            # Scan 40 baris pertama
            for i, row in df.head(40).iterrows():
                # Ubah baris jadi string kecil semua untuk pencarian
                row_text = " ".join(row.astype(str).lower())
                
                # KATA KUNCI: "berat" dan "end user" (ini ciri khas tabel mereka)
                if "berat" in row_text and "end user" in row_text:
                    
                    # Jadikan baris ini sebagai Header Kolom
                    df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                    data = df.iloc[i+1:].copy() # Ambil data di bawah header
                    
                    # Cari kolom yang kita butuhkan
                    c_berat = next((c for c in df.columns if "berat" in c), None)
                    c_jual = next((c for c in df.columns if "end user" in c), None)
                    c_stok = next((c for c in df.columns if "stock" in c or "stok" in c), None)
                    
                    if c_berat and c_jual:
                        # Bersihkan & Ambil Angka
                        data["weight_g"] = data[c_berat].apply(lambda x: _clean_number(x, is_float=True))
                        data["sell_idr"] = data[c_jual].apply(lambda x: _clean_number(x, is_float=False))
                        
                        if c_stok:
                            data["stock"] = data[c_stok].fillna("Ready")
                        else:
                            data["stock"] = "Ready"

                        # Filter: Hanya ambil yang berat > 0 dan harga > 0
                        valid_data = data[(data["weight_g"] > 0) & (data["sell_idr"] > 0)].copy()
                        
                        if not valid_data.empty:
                            # --- Cari Info Tambahan (Tanggal & Buyback) ---
                            # Gabungkan seluruh teks di sheet ini jadi satu paragraf panjang
                            full_text = " ".join(df.astype(str).values.flatten()).lower()
                            
                            # Regex Cari Tanggal (cth: 07 Feb 2026)
                            import re
                            dt = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", full_text)
                            if dt: label += f" — {dt.group(1).title()}"
                            
                            # Regex Cari Buyback (cth: Buyback 1.200.000)
                            bb = re.search(r"buyback.*?(\d[\d\.,]+)", full_text)
                            if bb:
                                buyback_val = _clean_number(bb.group(1))
                                label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")

                            valid_data["vendor"] = "HK Logam Mulia"
                            valid_data["buyback_idr"] = (valid_data["weight_g"] * buyback_val).astype(int)
                            
                            final_df = valid_data[["vendor", "weight_g", "sell_idr", "buyback_idr", "stock"]]
                            break # Sudah ketemu, berhenti scanning
            if not final_df.empty: break

        if final_df.empty:
            return pd.DataFrame(), "HK Logam Mulia — Tabel harga tidak ditemukan di dalam file"

        return final_df.sort_values("weight_g").reset_index(drop=True), label

    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Error: {str(e)}"

def _clean_number(val, is_float=False):
    """Membersihkan angka dari teks kotor (Rp, titik, koma, gr)"""
    import re
    if pd.isna(val) or val == "": return 0
    s = str(val).lower().replace("gr", "").replace("gram", "").strip()
    try:
        if is_float:
            # Ganti koma jadi titik (indo -> us format)
            s = s.replace(",", ".")
            return float(re.findall(r"[-+]?\d*\.\d+|\d+", s)[0])
        else:
            # Ambil angka bulat saja
            s = s.split(",")[0].split(".")[0] # Buang desimal
            return int(re.sub(r"[^\d]", "", s))
    except:
        return 0
