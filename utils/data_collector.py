import pandas as pd
import streamlit as st
import requests
from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold, URL_HAKABEGOLD
from scrapers.agungjewellery import parse_agungjewellery
from utils.history_manager import save_to_history

def fetch_html_silent(url: str) -> str:
    """Helper untuk mengambil HTML tanpa menampilkan error di UI."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        return r.text
    except:
        return ""

def sync_all_sources():
    """Menjalankan semua scraper dan menggabungkannya ke satu DataFrame."""
    all_results = []
    
    # List Vendor yang akan ditarik
    # 1. StarGold (Membaca file source web.txt)
    df_sg, _ = parse_stargold("")
    if not df_sg.empty: all_results.append(df_sg)
    
    # 2. Galeri24 (Live)
    html_g24 = fetch_html_silent(URL_GALERI24)
    df_g24, _ = parse_galeri24(html_g24)
    if not df_g24.empty: all_results.append(df_g24)
    
    # 3. Aneka Logam (Live)
    html_al = fetch_html_silent(URL_ANEKALOGAM)
    df_al, _ = parse_anekalogam(html_al)
    if not df_al.empty: all_results.append(df_al)
    
    # 4. Hakabe Gold (Live Google Sheets)
    html_hk = fetch_html_silent(URL_HAKABEGOLD)
    df_hk, _ = parse_hakabegold(html_hk)
    if not df_hk.empty: all_results.append(df_hk)
    
    # 5. IndoGold (Live)
    html_ig = fetch_html_silent(URL_INDOGOLD)
    df_ig, _ = parse_indogold(html_ig)
    if not df_ig.empty: all_results.append(df_ig)

    # Gabungkan semua jika ada data
    if all_results:
        df_master = pd.concat(all_results, ignore_index=True)
        # Simpan ke histori secara permanen
        save_to_history(df_master)
        return df_master
    return pd.DataFrame()
