# scrapers/hakabegold.py
from __future__ import annotations

import re
import pandas as pd
import requests
from io import BytesIO
from typing import Tuple, Optional
from urllib.parse import urlparse, urlunparse

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"
# Link cadangan hardcoded dari file Anda (sebagai fallback terakhir)
FALLBACK_LINK = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8"

def _session() -> requests.Session:
    s = requests.Session()
    # Menggunakan User-Agent Chrome Desktop terbaru agar dianggap user asli
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    })
    return s

def _convert_to_direct_download(final_url: str) -> str:
    """
    Mengubah URL View/Edit/Redir OneDrive menjadi URL Download paksa.
    Logika: Mengganti endpoint .aspx menjadi download.aspx dengan parameter yang sama.
    """
    parsed = urlparse(final_url)
    path = parsed.path.lower()
    
    # Daftar endpoint yang harus diubah menjadi download.aspx
    targets = ["/view.aspx", "/edit.aspx", "/redir.aspx", "/embed"]
    
    new_path = path
    converted = False
    
    for t in targets:
        if t in path:
            if t == "/embed":
                new_path = path.replace(t, "/download")
            else:
                new_path = path.replace(t, "/download.aspx")
            converted = True
            break
            
    if converted:
        # Konstruksi ulang URL dengan path baru, query params tetap sama
        return urlunparse(parsed._replace(path=new_path))
    
    # Jika URL sudah terlihat seperti download link atau format lain, kembalikan aslinya
    # tapi tambahkan parameter download=1 untuk memastikan
    if "download" not in path:
        sep = "&" if "?" in final_url else "?"
        return final_url + sep + "download=1"
        
    return final_url

def _resolve_onedrive_link(s: requests.Session, short_url: str) -> str:
    try:
        # 1. Ikuti redirect, tapi stream=True agar tidak download konten (hemat bandwidth)
        #    Kita hanya butuh URL akhirnya.
        r = s.get(short_url, allow_redirects=True, stream=True, timeout=20)
        final_url = r.url
        r.close() # Tutup koneksi karena kita cuma butuh URL
        
        # 2. Konversi URL akhir menjadi link download
        return _convert_to_direct_download(final_url)
    except Exception as e:
        print(f"[HakabeGold] Error resolving link: {e}")
        # Jika gagal resolve, coba konversi link mentah siapa tahu bisa
        return _convert_to_direct_download(short_url)

def _clean_currency(val) -> int:
    if pd.isna(val) or val == "": return 0
    # Hapus Rp, titik, koma, spasi, dan karakter non-digit
    s = str(val).split(",")[0] # Ambil bagian depan koma jika ada desimal (100.000,00)
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else 0

def _clean_float(val) -> float:
    if pd.isna(val): return 0.0
    s = str(val).lower().replace("gr", "").strip()
    s = s.replace(",", ".") # Ganti koma jadi titik untuk float
    try:
        return float(s)
    except:
        return 0.0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    s = _session()
    
    # 1. Dapatkan Link Awal
    target_link = ""
    
    # Coba ambil dari HTML
    if html:
        # Regex yang lebih permisif untuk menangkap src iframe
        iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if iframe_match:
            target_link = iframe_match.group(1).replace("&amp;", "&")
            
    # Jika tidak ketemu di HTML, gunakan Link Fallback
    if not target_link:
        target_link = FALLBACK_LINK

    # 2. Proses menjadi Link Download Biner
    download_url = _resolve_onedrive_link(s, target_link)
    
    # 3. Download File Excel
    try:
        r_file = s.get(download_url, timeout=45)
        
        # Cek jika masih dikasih HTML (biasanya karena cookie/auth issue)
        if "text/html" in r_file.headers.get("Content-Type", "").lower():
            # Retry mechanism: Kadang OneDrive butuh cookies dari request pertama
            # Kita coba sekali lagi dengan session yang sama (cookies tersimpan)
            r_file = s.get(download_url, timeout=45)
            
        if "text/html" in r_file.headers.get("Content-Type", "").lower():
             return pd.DataFrame(), "HK Logam Mulia — Gagal: OneDrive Access Denied (HTML Response)"
             
        excel_data = BytesIO(r_file.content)
        
    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — Gagal Download: {str(e)}"

    # 4. Parsing Excel (Scan Seluruh Sheet)
    try:
        xls = pd.read_excel(excel_data, sheet_name=None, header=None)
    except Exception:
        return pd.DataFrame(), "HK Logam Mulia — File bukan Excel valid"

    data_df = None
    asof_label = "HK Logam Mulia"
    buyback_val = 0

    for sheet_name, df in xls.items():
        # Bersihkan whitespace di seluruh dataframe
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        
        # Cari koordinat header
        header_idx = None
        for i, row in df.head(50).iterrows():
            row_str = " ".join(row.astype(str).str.lower())
            # Kata kunci kita perketat agar tidak salah ambil baris
            if "berat" in row_str and "harga" in row_str and "end user" in row_str:
                header_idx = i
                break
        
        if header_idx is not None:
            # Re-read bagian tabel saja
            df_table = df.iloc[header_idx+1:].copy()
            df_table.columns = df.iloc[header_idx].astype(str).str.lower().str.strip()
            
            # Cari kolom Berat dan Harga
            # Kita gunakan "in" karena nama kolom bisa "Berat (gr)" atau "Berat "
            col_berat = next((c for c in df_table.columns if "berat" in c), None)
            col_harga = next((c for c in df_table.columns if "end user" in c), None)
            
            if col_berat and col_harga:
                temp_df = df_table[[col_berat, col_harga]].copy()
                temp_df.columns = ["weight_g", "sell_raw"]
                
                # Cleaning Data
                temp_df["weight_g"] = temp_df["weight_g"].apply(_clean_float)
                temp_df["sell_idr"] = temp_df["sell_raw"].apply(_clean_currency)
                
                # Filter hanya yang datanya masuk akal (berat > 0 dan harga > 1000)
                temp_df = temp_df[(temp_df["weight_g"] > 0) & (temp_df["sell_idr"] > 1000)]
                
                if not temp_df.empty:
                    data_df = temp_df.copy()
                    
                    # --- Ekstrak Metadata (Tanggal & Buyback) dari sheet yang sama ---
                    # Ubah seluruh sheet jadi satu string panjang untuk regex
                    full_text = " ".join(df.astype(str).values.flatten())
                    
                    # Regex Tanggal: Mencari pola "dd Month yyyy"
                    # Contoh: 07 February 2026
                    date_match = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", full_text)
                    if date_match:
                        asof_label += f" — {date_match.group(1)}"
                        
                    # Regex Buyback: Mencari "Buyback ... angka"
                    bb_match = re.search(r"buyback\s*:?\s*(Rp)?\s*([\d\.,]+)", full_text, re.IGNORECASE)
                    if bb_match:
                        buyback_val = _clean_currency(bb_match.group(2))
                        asof_label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                        
                    break # Sudah ketemu, stop looping sheet

    if data_df is None:
        return pd.DataFrame(), "HK Logam Mulia — Struktur tabel Excel berubah"

    # 5. Final Formatting
    data_df["vendor"] = "HK Logam Mulia"
    data_df["buyback_idr"] = (data_df["weight_g"] * buyback_val).astype(int)
    
    # Sort dan Select Columns
    final_df = data_df[["vendor", "weight_g", "sell_idr", "buyback_idr"]].sort_values("weight_g").reset_index(drop=True)
    
    return final_df, asof_label
