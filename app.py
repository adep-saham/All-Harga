import streamlit as st
import requests
import pandas as pd
from io import BytesIO

# =========================================================
# IMPORT SCRAPERS & UTILS
# =========================================================
from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold, URL_HAKABEGOLD
from scrapers.agungjewellery import parse_agungjewellery

# Proteksi import utils
try:
    from utils.uploader import render_uploader_sidebar
    from utils.history_manager import get_full_history
except ImportError:
    def render_uploader_sidebar(): pass
    def get_full_history(): return pd.DataFrame()

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Monitoring Harga Emas",
    layout="wide"
)

# =========================================================
# HELPERS
# =========================================================
def format_rp(x):
    """Format angka ke Rupiah dengan pemisah titik."""
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"

@st.cache_data(ttl=300)
def fetch_html(url: str) -> str:
    """Generic HTML fetcher."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text or ""
    except Exception:
        return ""

def get_all_comparison_100g():
    """
    Mengumpulkan data 100g dari semua sumber.
    Filter 'Antam' hanya untuk toko yang multi-brand.
    """
    results = []
    # Daftar urutan sesuai permintaan di gambar
    scrapers = [
        ("StarGold", lambda: parse_stargold("")),
        ("Galeri 24", lambda: parse_galeri24(fetch_html(URL_GALERI24))),
        ("Aneka Logam", lambda: parse_anekalogam(fetch_html(URL_ANEKALOGAM))),
        ("HRTA", lambda: parse_hrta("")),
        ("IndoGold", lambda: parse_indogold(fetch_html(URL_INDOGOLD))),
        ("Hakabe Gold", lambda: parse_hakabegold()),
        ("Agung Jewellery", lambda: parse_agungjewellery()),
    ]

    for source_name, func in scrapers:
        try:
            df_tmp, _ = func()
            if df_tmp is not None and not df_tmp.empty:
                # LOGIKA FILTER DINAMIS:
                if source_name in ["Galeri 24", "StarGold", "IndoGold"]:
                    # Toko ini punya banyak brand, kita ambil yang ada kata 'ANTAM'
                    mask = (df_tmp['vendor'].str.contains('ANTAM', case=False, na=False)) & \
                           (df_tmp['weight_g'] == 100)
                else:
                    # Toko lain (HRTA, Hakabe, Aneka, Agung), ambil produk 100g utama mereka
                    mask = (df_tmp['weight_g'] == 100)
                
                filtered = df_tmp[mask].copy()
                if not filtered.empty:
                    # Ambil baris pertama (harga terendah/utama)
                    row = filtered.sort_values("sell_idr").iloc[0]
                    results.append({
                        "Nama Toko Emas": source_name,
                        "Harga Jual": row['sell_idr'],
                        "Harga Beli": row['buyback_idr']
                    })
        except Exception:
            # Jika satu vendor error, lewati saja agar vendor lain tetap muncul
            continue
            
    return pd.DataFrame(results)

# =========================================================
# UI SIDEBAR
# =========================================================
st.sidebar.title("⚙️ Kontrol")

source = st.sidebar.radio(
    "Sumber Data",
    [
        "📊 Perbandingan 100g (All)",
        "Galeri24",
        "StarGold",
        "AnekaLogam",
        "HRTA",
        "IndoGold",
        "HK Logam Mulia",
        "Agung Jewellery",
    ],
    index=0,
)

st.sidebar.divider()
render_uploader_sidebar()

# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")

if st.button("🚀 Ambil Data Sekarang", use_container_width=True, type="primary"):
    try:
        if source == "📊 Perbandingan 100g (All)":
            with st.spinner("Menyelaraskan harga 100g dari seluruh toko..."):
                df_comp = get_all_comparison_100g()
                if not df_comp.empty:
                    # Urutkan berdasarkan harga jual termurah
                    df_comp = df_comp.sort_values("Harga Jual", ascending=True).reset_index(drop=True)
                    df_comp.index += 1 # Penomoran mulai dari 1
                    
                    st.subheader("🏆 Tabel Perbandingan Emas 100 gr")
                    
                    # Tampilan Tabel Final
                    display_table = pd.DataFrame({
                        "No": df_comp.index,
                        "Nama Toko Emas": df_comp["Nama Toko Emas"],
                        "Harga Jual": df_comp["Harga Jual"].apply(format_rp),
                        "Harga Beli": df_comp["Harga Beli"].apply(format_rp)
                    })
                    st.table(display_table)
                    
                    # Highlight harga terbaik
                    best = df_comp.iloc[0]
                    st.success(f"Harga Termurah saat ini: **{format_rp(best['Harga Jual'])}** di **{best['Nama Toko Emas']}**")
                else:
                    st.warning("Data 100g tidak ditemukan di semua sumber.")

        else:
            # === LOGIKA DETAIL VENDOR (LAMA) ===
            with st.spinner(f"Mengambil data lengkap {source}..."):
                df = pd.DataFrame()
                update_label = ""
                
                URLS = {
                    "Galeri24": URL_GALERI24,
                    "StarGold": URL_STARGOLD,
                    "AnekaLogam": URL_ANEKALOGAM,
                    "HRTA": URL_HRTA,
                    "IndoGold": URL_INDOGOLD,
                    "HK Logam Mulia": URL_HAKABEGOLD,
                }

                if source == "HK Logam Mulia":
                    df, update_label = parse_hakabegold()
                elif source == "StarGold":
                    df, update_label = parse_stargold("")
                elif source == "Agung Jewellery":
                    df, update_label = parse_agungjewellery()
                elif source == "HRTA":
                    df, update_label = parse_hrta("")
                else:
                    html = fetch_html(URLS.get(source, ""))
                    if source == "Galeri24": df, update_label = parse_galeri24(html)
                    elif source == "AnekaLogam": df, update_label = parse_anekalogam(html)
                    elif source == "IndoGold": df, update_label = parse_indogold(html)

            if df is not None and not df.empty:
                st.subheader(update_label)
                for vendor in df["vendor"].unique():
                    st.markdown(f"### {vendor}")
                    sub = df[df["vendor"] == vendor].copy()
                    if "weight_g" in sub.columns: sub = sub.sort_values("weight_g")
                    
                    display = pd.DataFrame({
                        "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                        "Harga Jual": sub["sell_idr"].apply(format_rp),
                        "Harga Buyback": sub["buyback_idr"].apply(format_rp),
                        "Stok": sub.get("stock", "Ready"),
                    })
                    st.table(display)
            else:
                st.warning("Data kosong atau gagal diambil.")

    except Exception as e:
        st.error(f"Terjadi kesalahan fatal: {e}")
