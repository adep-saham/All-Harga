# scrapers/hakabegold.py
from __future__ import annotations

import re
import pandas as pd
import requests
from io import BytesIO
from typing import Tuple, Optional, Any
from urllib.parse import urlparse, urlunparse

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

# Link asli dari htlm.txt yang Anda kirim
FALLBACK_LINK = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8"

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    })
    return s

def _try_download(s: requests.Session, url: str) -> Optional[BytesIO]:
    """Mencoba download dengan timeout dan error handling."""
    try:
        r = s.get(url, timeout=30, allow_redirects=True)
        # Cek apakah hasilnya HTML (gagal) atau Binary (berhasil)
        content_type = r.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and len(r.content) > 1000:
            return BytesIO(r.content)
    except Exception:
        pass
    return None

def _resolve_onedrive_aggressive(s: requests.Session, short_url: str) -> Optional[BytesIO]:
    """
    Mencoba 3 strategi untuk mendapatkan file dari OneDrive Short Link.
    """
    # STRATEGI 1: Ikuti Redirect -> Ubah .aspx jadi download.aspx
    try:
        r = s.get(short_url, timeout=20, allow_redirects=True, stream=True)
        final_url = r.url
        r.close() # Tutup koneksi, kita cuma butuh URL akhir
        
        parsed = urlparse(final_url)
        path = parsed.path.lower()
        
        # Ubah endpoint view/edit menjadi download
        if "view.aspx" in path or "edit.aspx" in path or "redir.aspx" in path:
            new_path = path.replace("view.aspx", "download.aspx") \
                           .replace("edit.aspx", "download.aspx") \
                           .replace("redir.aspx", "download.aspx")
            download_link = urlunparse(parsed._replace(path=new_path))
            
            data = _try_download(s, download_link)
            if data: return data
    except:
        pass

    # STRATEGI 2: Tambah parameter &download=1 ke URL akhir
    try:
        if "?" in final_url:
            download_link_2 = final_url + "&download=1"
        else:
            download_link_2 = final_url + "?download=1"
        
        data = _try_download(s, download_link_2)
        if data: return data
    except:
        pass

    # STRATEGI 3: Gunakan API export (khusus file Excel)
    # Ini kadang bypass tampilan web
    try:
        if "?" in final_url:
            download_link_3 = final_url + "&export=download&format=xlsx"
        else:
            download_link_3 = final_url + "?export=download&format=xlsx"
            
        data = _try_download(s, download_link_3)
        if data: return data
    except:
        pass
        
    return None

def _clean_currency(val: Any) -> int:
    if pd.isna(val): return 0
    s = str(val).split(",")[0] # Ambil angka sebelum koma (desimal uang dibuang)
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else 0

def _clean_float(val: Any) -> float:
    if pd.isna(val): return 0.0
    s = str(val).lower().replace("gr", "").strip()
    s = s.replace(",", ".") # Ganti koma jadi titik
    try:
        return float(s)
    except:
        return 0.0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    s = _session()
    
    # 1. Tentukan Link Target
    # Prioritas: Link yang ditemukan di HTML (jika ada), jika tidak gunakan FALLBACK
    target_link = FALLBACK_LINK
    
    if html:
        iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if iframe_match:
            # Bersihkan URL dari entity HTML
            found_link = iframe_match.group(1).replace("&amp;", "&")
            # Pastikan itu link OneDrive
            if "onedrive" in found_link or "1drv.ms" in found_link:
                target_link = found_link

    # 2. Eksekusi Download Agresif
    excel_data = _resolve_onedrive_aggressive(s, target_link)
    
    if not excel_data:
        # Pesan error spesifik untuk debug
        return pd.DataFrame(), "HK Logam Mulia — Gagal: OneDrive menolak akses (Blokir Bot)"

    # 3. Parsing Excel (Scan Seluruh Sheet)
    try:
        # Load semua sheet, header=None supaya kita cari manual baris headernya
        xls = pd.read_excel(excel_data, sheet_name=None, header=None)
    except Exception as e:
        return pd.DataFrame(), f"HK Logam Mulia — File rusak/Bukan Excel ({str(e)})"

    data_df = None
    asof_label = "HK Logam Mulia"
    buyback_val = 0

    for sheet_name, df in xls.items():
        # Konversi semua ke string lowercase untuk pencarian
        # Buat dataframe bayangan untuk searching text
        df_str = df.astype(str).apply(lambda x: x.str.lower())
        
        # Cari koordinat baris yang mengandung 'berat' dan 'harga'
        header_found = False
        header_idx = -1
        
        # Scan 50 baris pertama
        for i in range(min(len(df), 50)):
            row_vals = df_str.iloc[i].values
            row_text = " ".join(row_vals)
            if "berat" in row_text and "end user" in row_text:
                header_idx = i
                header_found = True
                break
        
        if header_found:
            # Ambil data mulai dari baris header + 1
            df_table = df.iloc[header_idx+1:].copy()
            # Set nama kolom dari baris header
            df_table.columns = df.iloc[header_idx].astype(str).str.lower().str.strip()
            
            # Cari kolom kunci
            col_berat = next((c for c in df_table.columns if "berat" in c), None)
            col_harga = next((c for c in df_table.columns if "end user" in c), None) # Harga End User
            
            if col_berat and col_harga:
                temp = pd.DataFrame()
                temp["weight_g"] = df_table[col_berat].apply(_clean_float)
                temp["sell_idr"] = df_table[col_harga].apply(_clean_currency)
                
                # Filter data sampah (berat 0 atau harga 0)
                temp = temp[(temp["weight_g"] > 0) & (temp["sell_idr"] > 1000)]
                
                if not temp.empty:
                    data_df = temp.copy()
                    
                    # --- Ekstrak Tanggal & Buyback dari sheet yang sama ---
                    full_text = " ".join(df_str.values.flatten())
                    
                    # Regex Tanggal (contoh: 07 feb 2026)
                    date_m = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", full_text)
                    if date_m:
                        asof_label += f" — {date_m.group(1).title()}"
                    
                    # Regex Buyback
                    bb_m = re.search(r"buyback.*?(\d[\d\.,]+)", full_text)
                    if bb_m:
                        buyback_val = _clean_currency(bb_m.group(1))
                        asof_label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                        
                    break # Ketemu tabel valid, stop loop sheet

    if data_df is None:
        return pd.DataFrame(), "HK Logam Mulia — Struktur tabel Excel berubah"

    # 4. Finalisasi
    data_df["vendor"] = "HK Logam Mulia"
    data_df["buyback_idr"] = (data_df["weight_g"] * buyback_val).astype(int)
    
    # Sort
    final_df = data_df[["vendor", "weight_g", "sell_idr", "buyback_idr"]].sort_values("weight_g").reset_index(drop=True)
    
    return final_df, asof_label
