import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

# Link OneDrive 1drv.ms milik Anda
MY_SHORT_LINK = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8"

# Dummy variable agar app.py aman
URL_HAKABEGOLD = MY_SHORT_LINK

def resolve_onedrive_link(short_url):
    """
    Fungsi Penjelajah:
    1. Mengakses link pendek (1drv.ms).
    2. Mengikuti pengalihan (redirect) sampai ke alamat asli (onedrive.live.com).
    3. Mengubah alamat 'View/Edit' menjadi 'Download'.
    """
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 1. Ikuti Redirect sampai mentok
        # allow_redirects=True artinya "Jangan berhenti di pintu depan, masuk terus sampai tujuan akhir"
        response = session.get(short_url, headers=headers, timeout=30, allow_redirects=True)
        
        final_url = response.url
        
        # 2. Modifikasi URL Akhir
        # URL akhir biasanya berbentuk: https://onedrive.live.com/edit.aspx?... atau view.aspx?...
        # Kita ganti bagian itu menjadi 'download'
        
        if "onedrive.live.com" in final_url:
            # Ganti variasi apapun (edit, view, redir) menjadi 'download'
            download_url = re.sub(r"/(edit|view|redir|embed)\.aspx", "/download", final_url)
            
            # Bersihkan parameter sampah yang mungkin menghalangi download
            download_url = download_url.replace("&action=edit", "").replace("&app=Excel", "")
            
            return download_url
            
        # Jika redirect gagal tapi masih 1drv.ms, coba cara kasar tambah parameter download
        return short_url + "?download=1"

    except Exception as e:
        print(f"Gagal resolve link: {e}")
        return short_url

def parse_hakabegold(dummy_html="") -> Tuple[pd.DataFrame, str]:
    try:
        # LANGKAH 1: Resolve Link
        download_url = resolve_onedrive_link(MY_SHORT_LINK)
        
        # LANGKAH 2: Download
        headers = {"User-Agent": "Mozilla/5.0"}
        # Timeout agak lama (60s) jaga-jaga server lambat
        response = requests.get(download_url, headers=headers, timeout=60)
        
        if response.status_code != 200:
            return pd.DataFrame(), f"Gagal Akses (Code: {response.status_code})"

        # LANGKAH 3: Baca Excel
        # Kita pakai engine openpyxl yang sudah terinstall
        try:
            xls_data = BytesIO(response.content)
            xls = pd.read_excel(xls_data, sheet_name=None, header=None, engine='openpyxl')
        except Exception:
            # Jika gagal, cek apakah itu HTML (berarti link masih salah)
            if b"<!DOCTYPE html>" in response.content[:100]:
                return pd.DataFrame(), "Link mengarah ke Web View. Gagal convert ke Download."
            return pd.DataFrame(), "File rusak atau bukan Excel."

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"
        buyback_val = 0

        # LANGKAH 4: Cari Tabel Data
        for sheet_name, df in xls.items():
            # Scan 50 baris pertama
            for i, row in df.head(50).iterrows():
                row_text = " ".join(row.astype(str).lower())
                
                # KATA KUNCI: "berat" dan "end user" (Header tabel)
                if "berat" in row_text and "end user" in row_text:
                    
                    df.columns = df.iloc[i].astype(str).str.lower().str.strip()
                    data = df.iloc[i+1:].copy()
                    
                    c_berat = next((c for c in df.columns if "berat" in c), None)
                    c_jual = next((c for c in df.columns if "end user" in c), None)
                    c_stok = next((c for c in df.columns if "stock" in c or "stok" in c), None)
                    
                    if c_berat and c_jual:
                        # Bersihkan Data
                        data["weight_g"] = data[c_berat].apply(lambda x: _clean_number(x, is_float=True))
                        data["sell_idr"] = data[c_jual].apply(lambda x: _clean_number(x, is_float=False))
                        
                        if c_stok:
                            data["stock"] = data[c_stok].fillna("Ready")
                        else:
                            data["stock"] = "Ready"
                        
                        valid = data[(data["weight_g"] > 0) & (data["sell_idr"] > 0)].copy()
                        
                        if not valid.empty:
                            # Cari Metadata (Tanggal & Buyback)
                            full_text = " ".join(df.astype(str).values.flatten()).lower()
                            
                            dt = re.search(r"(\d{1,2}\s+[a-z]{3,}\s+\d{4})", full_text)
                            if dt: label += f" — {dt.group(1).title()}"
                            
                            bb = re.search(r"buyback.*?(\d[\d\.,]+)", full_text)
                            if bb:
                                buyback_val = _clean_number(bb.group(1))
                                label += f" — Buyback: Rp{buyback_val:,}".replace(",", ".")
                            
                            valid["vendor"] = "HK Logam Mulia"
                            valid["buyback_idr"] = (valid["weight_g"] * buyback_val).astype(int)
                            final_df = valid[["vendor", "weight_g", "sell_idr", "buyback_idr", "stock"]]
                            break
            if not final_df.empty: break

        if final_df.empty:
            return pd.DataFrame(), "Tabel harga tidak ditemukan di file Excel."

        return final_df.sort_values("weight_g").reset_index(drop=True), label

    except Exception as e:
        return pd.DataFrame(), f"Error System: {str(e)}"

def _clean_number(val, is_float=False):
    if pd.isna(val) or val == "": return 0
    s = str(val).lower().replace("gr", "").replace("gram", "").strip()
    try:
        if is_float:
            s = s.replace(",", ".")
            matches = re.findall(r"[-+]?\d*\.\d+|\d+", s)
            return float(matches[0]) if matches else 0
        else:
            s = s.split(",")[0].split(".")[0]
            cleaned = re.sub(r"[^\d]", "", s)
            return int(cleaned) if cleaned else 0
    except:
        return 0
