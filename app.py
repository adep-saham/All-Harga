import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime

# =========================================================
# 1. IMPORT SCRAPERS & UTILS
# =========================================================
from scrapers.galeri24 import parse_galeri24
from scrapers.stargold import parse_stargold
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold
from scrapers.agungjewellery import parse_agungjewellery

from utils.uploader import render_uploader_sidebar
from utils.history_manager import get_full_history, save_to_history

# =========================================================
# 2. CONFIG & HELPERS
# =========================================================
st.set_page_config(page_title="Monitor Harga Emas", layout="wide")

def format_rp(x):
    try: return f"Rp{int(x):,}".replace(",", ".")
    except: return "Rp0"

@st.cache_data(ttl=300)
def fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        return r.text or ""
    except: return ""

# =========================================================
# 3. SIDEBAR & CONTROL
# =========================================================
with st.sidebar:
    st.title("⚙️ Kontrol Panel")
    if st.button("🚀 Tarik Data Sekarang", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    render_uploader_sidebar()

# =========================================================
# 4. TAMPILAN UTAMA
# =========================================================
tab1, tab2 = st.tabs(["📊 Perbandingan & Detail", "📈 Histori & Grafik"])

with tab1:
    st.header("Harga Emas Hari Ini")
    
    # List untuk menampung data semua vendor
    all_vendors_data = {}
    summary_100g = []

    # --- PROSES PENGAMBILAN DATA (SEMUA VENDOR) ---
    # 1. Galeri 24
    try:
        df, lbl = parse_galeri24()
        all_vendors_data["Galeri 24"] = (df, lbl)
        d100 = df[df['weight_g'] == 100]
        if not d100.empty:
            summary_100g.append({"vendor": "Galeri 24", "sell": d100.iloc[0]['sell_idr'], "buy": d100.iloc[0]['buyback_idr'], "update": lbl})
    except: pass

    # 2. Aneka Logam
    try:
        df, lbl = parse_anekalogam(fetch_html(URL_ANEKALOGAM))
        all_vendors_data["Aneka Logam"] = (df, lbl)
        d100 = df[df['weight_g'] == 100]
        if not d100.empty:
            summary_100g.append({"vendor": "Aneka Logam", "sell": d100.iloc[0]['sell_idr'], "buy": d100.iloc[0]['buyback_idr'], "update": lbl})
    except: pass

    # 3. StarGold
    try:
        df, lbl = parse_stargold("")
        all_vendors_data["StarGold"] = (df, lbl)
        d100 = df[df['weight_g'] == 100]
        if not d100.empty:
            summary_100g.append({"vendor": "StarGold", "sell": d100.iloc[0]['sell_idr'], "buy": d100.iloc[0]['buyback_idr'], "update": lbl})
    except: pass

    # 4. HRTA
    try:
        df, lbl = parse_hrta(fetch_html(URL_HRTA))
        all_vendors_data["HRTA"] = (df, lbl)
        d100 = df[df['weight_g'] == 100]
        if not d100.empty:
            summary_100g.append({"vendor": "HRTA", "sell": d100.iloc[0]['sell_idr'], "buy": d100.iloc[0]['buyback_idr'], "update": lbl})
    except: pass

    # 5. HK Logam Mulia
    try:
        df, lbl = parse_hakabegold()
        all_vendors_data["HK Logam Mulia"] = (df, lbl)
        d100 = df[df['weight_g'] == 100]
        if not d100.empty:
            summary_100g.append({"vendor": "HK Logam Mulia", "sell": d100.iloc[0]['sell_idr'], "buy": d100.iloc[0]['buyback_idr'], "update": lbl})
    except: pass

    # --- A. BAGIAN RINGKASAN 100G ---
    st.subheader("🏆 Ringkasan Perbandingan (Pecahan 100g)")
    if summary_100g:
        df_sum = pd.DataFrame(summary_100g)
        view_sum = pd.DataFrame({
            "Vendor": df_sum["vendor"],
            "Harga Jual": df_sum["sell"].apply(format_rp),
            "Harga Beli": df_sum["buy"].apply(format_rp),
            "Update Web": df_sum["update"]
        })
        st.dataframe(view_sum, use_container_width=True, hide_index=True)
        
        if st.button("💾 Simpan Ringkasan 100g ke Histori"):
            df_save = pd.DataFrame({
                "vendor": df_sum["vendor"], "weight_g": 100,
                "sell_idr": df_sum["sell"], "buyback_idr": df_sum["buy"],
                "source_update": df_sum["update"]
            })
            if save_to_history(df_save, "Summary_100g"):
                st.success("✅ Histori Summary_100g diperbarui!")
    
    st.divider()

    # --- B. BAGIAN DETAIL PER TOKO (SEMUA PECAHAN) ---
    st.subheader("🏢 Detail Harga Lengkap Per Vendor")
    
    if all_vendors_data:
        # Gunakan kolom untuk menampilkan detail agar tidak terlalu panjang ke bawah
        for v_name, (df_v, lbl_v) in all_vendors_data.items():
            with st.expander(f"🔍 Detail {v_name} - {lbl_v}"):
                display_v = df_v.copy()
                display_v['Harga Jual'] = display_v['sell_idr'].apply(format_rp)
                display_v['Harga Beli'] = display_v['buyback_idr'].apply(format_rp)
                display_v['Berat'] = display_v['weight_g'].apply(lambda x: f"{x:g} gr")
                
                st.table(display_v[['Berat', 'Harga Jual', 'Harga Beli']])
                
                # Tombol simpan per vendor jika ingin simpan semua pecahan
                if st.button(f"Simpan Histori Lengkap {v_name}", key=f"btn_{v_name}"):
                    df_v['source_update'] = lbl_v
                    tab_name = v_name.replace(" ", "_")
                    if save_to_history(df_v, tab_name):
                        st.success(f"✅ Data {v_name} disimpan ke tab {tab_name}!")
    else:
        st.info("Data belum tersedia. Silakan klik 'Tarik Data Sekarang'.")

# =========================================================
# 5. TAB HISTORI & GRAFIK
# =========================================================
with tab2:
    st.header("📈 Analisis Histori")
    sheet_opt = st.selectbox("Pilih Sumber Data", ["Summary_100g", "StarGold", "AnekaLogam", "HK_Logam_Mulia", "Galeri24", "HRTA"])
    
    df_hist = get_full_history(sheet_opt)
    
    if not df_hist.empty:
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        
        c1, c2 = st.columns(2)
        v_sel = c1.selectbox("Pilih Vendor", sorted(df_hist['vendor'].unique()))
        w_sel = c2.selectbox("Pilih Berat", sorted(df_hist[df_hist['vendor']==v_sel]['weight_g'].unique()))
        
        plot_df = df_hist[(df_hist['vendor'] == v_sel) & (df_hist['weight_g'] == w_sel)].sort_values("timestamp")
        
        if not plot_df.empty:
            fig = px.line(plot_df, x="timestamp", y="sell_idr", markers=True, title=f"Tren {v_sel} {w_sel}g")
            st.plotly_chart(fig, use_container_width=True)
            
        with st.expander("📂 Lihat Data Mentah"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.warning("Belum ada histori.")
