# scrapers/hakabegold.py
from __future__ import annotations

import re
import pandas as pd
import requests
from io import BytesIO
from typing import Tuple, Optional
from urllib.parse import urlparse, parse_qs, unquote

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    })
    return s

def _resolve_onedrive_direct_link(s: requests.Session, short_url: str) -> Optional[str]:
    """
    Mengubah short link (1drv.ms) menjadi direct download link (onedrive.live.com/download).
    """
    try:
        # 1. Ikuti redirect dari 1drv.ms untuk mendapatkan URL asli
        # Kita set allow_redirects=True agar requests otomatis mengikuti sampai ujung
        response = s.get(short_url, timeout=20, allow_redirects=True)
        final_url = response.url
        
        # 2. Parsing URL akhir untuk mencari 'resid' dan 'authkey'
        parsed = urlparse(final_url)
        params = parse_qs(parsed.query)
        
        # resid biasanya ada di query param, kadang huruf besar/kecil
        resid = None
        for key in params.keys():
            if key.lower() == "resid":
                resid = params[key][0]
                break
        
        authkey = None
        for key in params.keys():
            if key.lower() == "authkey":
                authkey = params[key][0]
                break

        # Jika resid tidak ketemu di query, kadang dia ada di fragment atau path
        # Tapi untuk tipe link ini, kita coba cari pola resid di text URL-nya
        if not resid:
            match_resid = re.search(r'resid=([A-Z0-9!]+)', final_url, re.IGNORECASE)
            if match_resid:
                resid = match_resid.group(1)

        if not resid:
            # Gagal menemukan ID file
            return None

        # 3. Konstruksi Link Download Pasti
        # Menggunakan endpoint 'download' memaksa server mengirim byte file, bukan HTML preview
        direct_link = f"https://onedrive.live.com/download?resid={resid}"
        if authkey:
            direct_link += f"&authkey={authkey}"
            
        return direct_link
        
    except Exception as e:
        print(f"Error resolving OneDrive link: {e}")
        return None

def _clean_currency(val) -> int:
    if pd.isna(val) or val == "": return 0
    # Hapus Rp, titik, koma, spasi
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits else 0

def parse_hakabegold(html: str = "") -> Tuple[pd.DataFrame, str]:
    s = _session()
    
    # Jika HTML kosong, ambil dari web
    if not html:
        try:
            r = s.get(URL_HAKABEGOLD, timeout=15)
            html = r.text
        except Exception:
            return pd.DataFrame(), "HK Logam Mulia — Gagal Koneksi Website"

    # 1. Ekstrak Link Iframe dari HTML (sesuai htlm.txt)
    # Mencari src="..." di dalam tag iframe
    iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    
    if not iframe_match:
        return pd.DataFrame(), "HK Logam Mulia — Iframe OneDrive tidak ditemukan"
    
    # URL mentah dari HTML (misal: https://1drv.ms/x/c/...)
    raw_iframe_url = iframe_match.group(1)
    
    # Bersihkan entity HTML jika ada (misal &amp; jadi &)
    raw_iframe_url = raw_iframe_url.replace("&amp;", "&")

    # 2. Resolve menjadi Link Download
    download_url = _resolve_onedrive_direct_link(s, raw_iframe_url)
    
    if not download_url:
        return pd.DataFrame(), "HK Logam Mulia — Gagal resolve link OneDrive"

    # 3. Download File Excel
    try:
        r_file = s.get(download_url, timeout=45)
        r_file.raise_for_status()
        
        # Validasi konten: Pastikan bukan HTML
        content_type = r_file.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            return pd.DataFrame(), "HK Logam Mulia — OneDrive mengembalikan HTML (Access Denied/Busy)"
            
        excel_data = BytesIO(r_file.content)
    except Exception:
        return pd.DataFrame(), "HK Logam Mulia — Gagal download file Excel"

    # 4. Parsing Excel
    # Kita baca semua sheet karena nama sheet bisa berubah (Sheet1, Sheet2, dll)
    try:
        xls = pd.read_excel(excel_data, sheet_name=None, header=None)
    except Exception:
        return pd.DataFrame(), "HK Logam Mulia — File rusak atau bukan Excel"

    data_df = None
    asof_label = "HK Logam Mulia"
    buyback_val = 0

    for sheet_name, df in xls.items():
        # Cari baris header yang mengandung 'Berat' dan 'Harga End User'
        # Kita scan 50 baris pertama
        header_idx = None
        for i, row in df.head(50).iterrows():
            row_text = " ".join(row.astype(str).str.lower())
            if "berat" in row_text and "harga end user" in row_text:
                header_idx = i
                break
        
        if header_idx is not None:
            # Set header
            df.columns = df.iloc[header_idx].astype(str).str.strip()
            df = df.iloc[header_idx+1:].copy()
            
            # Normalisasi nama kolom (huruf kecil semua untuk pencarian)
            cols_map = {c: c.lower() for c in df.columns}
            
            # Cari kolom target
            col_berat = next((orig for orig, lower in cols_map.items() if "berat" in lower), None)
            col_harga = next((orig for orig, lower in cols_map.items() if "harga end user" in lower), None)
            
            if col_berat and col_harga:
                # Bersihkan data
                temp_df = df[[col_berat, col_harga]].copy()
                temp_df.columns = ["weight_g", "sell_raw"]
                
                # Konversi Berat (handle koma/titik)
                def clean_weight(x):
                    try:
                        return float(str(x).replace(",", "."))
                    except:
                        return 0.0
                
                temp_df["weight_g"] = temp_df["weight_g"].apply(clean_weight)
                temp_df["sell_idr"] = temp_df["sell_raw"].apply(_clean_currency)
                
                # Filter data valid
                valid_data = temp_df[(temp_df["weight_g"] > 0) & (temp_df["sell_idr"] > 1000)]
                
                if not valid_data.empty:
                    data_df = valid_data
                    
                    # --- Ekstrak Tanggal & Buyback dari sheet yang sama ---
                    full_text = " ".join(df.astype(str).values.flatten())
                    
                    # Regex Tanggal (contoh: 07 February 2026 atau 07 Feb 2026)
                    date_match = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", full_text)
                    if date_match:
                        asof_label += f" — {date_match.group(1)}"
                    
                    # Regex Buyback (Buyback ... /gram atau Buyback : Rp ...)
                    bb_match = re.search(r"buyback.*?(\d[\d\.,]+)", full_text, re.IGNORECASE)
                    if bb_match:
                        buyback_val = _clean_currency(bb_match.group(1))
                        asof_label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                    
                    # Ketemu tabel valid, berhenti loop sheet
                    break

    if data_df is None:
        return pd.DataFrame(), "HK Logam Mulia — Struktur tabel berubah/tidak ditemukan"

    # Format Output Akhir
    data_df["vendor"] = "HK Logam Mulia"
    # Hitung total buyback
    data_df["buyback_idr"] = (data_df["weight_g"] * buyback_val).astype(int)
    
    final_df = data_df[["vendor", "weight_g", "sell_idr", "buyback_idr"]].sort_values("weight_g").reset_index(drop=True)
    
    return final_df, asof_label
