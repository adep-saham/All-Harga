import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import plotly.express as px
from datetime import datetime

# =========================================================
# LIBRARY GOOGLE DRIVE
# =========================================================
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

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

from utils.uploader import render_uploader_sidebar
from utils.history_manager import get_full_history, save_to_history

# =========================================================
# CONFIG & HELPERS
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

# --- Helper Upload ke Google Drive ---
def upload_to_drive(excel_bytes, filename, folder_id):
    """Mengupload file bytes langsung ke Google Drive Folder tertentu"""
    try:
        # Mengambil kredensial dari st.secrets (sama seperti GSheets)
        # Pastikan secrets.toml Anda memiliki section [connections.gsheets]
        creds_dict = dict(st.secrets["connections"]["gsheets"])
        
        # Scope khusus untuk upload file
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
        
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': filename,
            'parents': [folder_id] # Upload ke dalam folder spesifik
        }
        
        media = MediaIoBaseUpload(
            excel_bytes, 
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink'
        ).execute()
        
        return file.get('webViewLink')
        
    except Exception as e:
        st.error(f"Gagal Upload ke Drive: {e}")
        return None

def get_all_comparison_100g():
    results = []
    scrapers = [
        ("StarGold", lambda: parse_stargold("")),
        ("Galeri 24", lambda: parse_galeri24(fetch_html(URL_GALERI24))),
        ("Aneka Logam", lambda: parse_anekalogam(fetch_html(URL_ANEKALOGAM))),
        ("HRTA GOLD", lambda: parse_hrta("")),
        ("IndoGold", lambda: parse_indogold(fetch_html(URL_INDOGOLD))),
        ("HK Logam Mulia", lambda: parse_hakabegold()),
        ("Agung Jewellery", lambda: parse_agungjewellery()),
    ]
    for name, func in scrapers:
        try:
            df_tmp, update_label = func() 
            if df_tmp is not None and not df_tmp.empty:
                if name in ["Galeri 24", "StarGold", "IndoGold"]:
                    mask = (df_tmp['vendor'].str.contains('ANTAM', case=False)) & (df_tmp['weight_g'] == 100)
                else:
                    mask = (df_tmp['weight_g'] == 100)
                filtered = df_tmp[mask].copy()
                if not filtered.empty:
                    row = filtered.sort_values("sell_idr").iloc[0]
                    results.append({
                        "vendor": name, "weight_g": 100, 
                        "sell_idr": row['sell_idr'], "buyback_idr": row['buyback_idr'],
                        "source_update": update_label 
                    })
        except: continue
    return pd.DataFrame(results)

def fetch_all_vendors_full():
    all_data = []
    scrapers = [
        ("StarGold", lambda: parse_stargold("")),
        ("Galeri 24", lambda: parse_galeri24(fetch_html(URL_GALERI24))),
        ("Aneka Logam", lambda: parse_anekalogam(fetch_html(URL_ANEKALOGAM))),
        ("HRTA GOLD", lambda: parse_hrta("")),
        ("IndoGold", lambda: parse_indogold(fetch_html(URL_INDOGOLD))),
        ("HK Logam Mulia", lambda: parse_hakabegold()),
        ("Agung Jewellery", lambda: parse_agungjewellery()),
    ]
    
    progress_text = "Menarik data toko..."
    my_bar = st.progress(0, text=progress_text)
    
    for i, (name, func) in enumerate(scrapers):
        try:
            my_bar.progress((i / len(scrapers)), text=f"Scraping: {name}...")
            df_tmp, update_label = func()
            if df_tmp is not None and not df_tmp.empty:
                df_tmp['source_update'] = update_label
                if 'vendor' not in df_tmp.columns: df_tmp['vendor'] = name
                all_data.append(df_tmp)
        except: pass
            
    my_bar.progress(1.0, text="Selesai.")
    if all_data:
        full = pd.concat(all_data, ignore_index=True)
        full['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return full
    return pd.DataFrame()

def create_excel_bytes(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Sheet Summary
        df_100 = df[df['weight_g'] == 100].copy()
        if not df_100.empty:
            df_100.to_excel(writer, index=False, sheet_name='Summary_100g')
        # Sheet Per Vendor
        for vendor in df['vendor'].unique():
            clean_name = str(vendor).replace(" ", "_").replace("/", "")[:30]
            df[df['vendor'] == vendor].to_excel(writer, index=False, sheet_name=clean_name)
    output.seek(0) # Reset pointer
    return output

# =========================================================
# UI SIDEBAR
# =========================================================
st.sidebar.title("⚙️ Kontrol")
mode = st.sidebar.radio("Mode Tampilan", ["📊 Perbandingan 100g (All)", "🏪 Detail Per Toko"])

if mode == "🏪 Detail Per Toko":
    source_opt = st.sidebar.selectbox("Pilih Toko", ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia", "Agung Jewellery"])
else:
    source_opt = "All 100g"

btn_fetch = st.sidebar.button("🚀 Lihat Data (View Only)", width='stretch')

st.sidebar.divider()
st.sidebar.subheader("☁️ Simpan ke Drive")

# Input Folder ID (Agar user bisa ganti-ganti folder jika perlu)
folder_id_input = st.sidebar.text_input("ID Folder Google Drive", help="Paste ID Folder dari URL Google Drive Anda")

if st.sidebar.button("⚡ Generate & Upload ke Drive", type="primary", width='stretch'):
    if not folder_id_input:
        st.sidebar.error("⚠️ Masukkan ID Folder Drive dulu!")
    else:
        with st.spinner("Sedang scraping & upload..."):
            # 1. Tarik Data
            df_full = fetch_all_vendors_full()
            
            if not df_full.empty:
                # 2. Buat Excel di Memory
                excel_io = create_excel_bytes(df_full)
                
                # 3. Upload ke Drive
                timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
                file_name = f"Rekap_Emas_{timestamp_str}.xlsx"
                
                link = upload_to_drive(excel_io, file_name, folder_id_input)
                
                if link:
                    st.sidebar.success("✅ Berhasil Terupload!")
                    st.sidebar.markdown(f"[📂 Buka File di Drive]({link})", unsafe_allow_html=True)
                    st.toast("File berhasil disimpan di Google Drive!", icon="☁️")
                    st.session_state['current_df'] = df_full # Tampilkan preview
            else:
                st.error("Data kosong, tidak ada yang diupload.")

st.sidebar.divider()
render_uploader_sidebar()

# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")
tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📈 Grafik Histori"])

with tab1:
    if btn_fetch:
        st.cache_data.clear()
        if mode == "📊 Perbandingan 100g (All)":
            st.session_state['current_df'] = get_all_comparison_100g()
        else:
            df_detail = pd.DataFrame()
            if source_opt == "HK Logam Mulia": df_detail, ul = parse_hakabegold()
            elif source_opt == "StarGold": df_detail, ul = parse_stargold("")
            elif source_opt == "Agung Jewellery": df_detail, ul = parse_agungjewellery()
            elif source_opt == "HRTA": df_detail, ul = parse_hrta("")
            else:
                url = {"Galeri24": URL_GALERI24, "AnekaLogam": URL_ANEKALOGAM, "IndoGold": URL_INDOGOLD}.get(source_opt)
                html = fetch_html(url)
                if source_opt == "Galeri24": df_detail, ul = parse_galeri24(html)
                elif source_opt == "AnekaLogam": df_detail, ul = parse_anekalogam(html)
                elif source_opt == "IndoGold": df_detail, ul = parse_indogold(html)
            
            if not df_detail.empty: df_detail['source_update'] = ul
            st.session_state['current_df'] = df_detail

    if 'current_df' in st.session_state and not st.session_state['current_df'].empty:
        df_active = st.session_state['current_df']
        
        if mode == "📊 Perbandingan 100g (All)" and df_active["vendor"].nunique() > 1:
            st.subheader("📋 Tabel Perbandingan Antam 100 gr")
            # Filter visual jika data campur
            df_view = df_active[df_active['weight_g'] == 100].copy() if 'weight_g' in df_active.columns else df_active
            
            df_table = df_view.sort_values("sell_idr").reset_index(drop=True)
            st.dataframe(pd.DataFrame({
                "No": range(1, len(df_table) + 1),
                "Nama Toko": df_table["vendor"],
                "Jual": df_table["sell_idr"].apply(format_rp),
                "Beli": df_table["buyback_idr"].apply(format_rp),
                "Update": df_table["source_update"]
            }), width='stretch', hide_index=True)
            
        elif mode == "🏪 Detail Per Toko" or df_active["vendor"].nunique() == 1:
            v_name = df_active["vendor"].iloc[0]
            st.subheader(f"🏢 {v_name}")
            sub = df_active.sort_values("weight_g")
            st.table(pd.DataFrame({
                "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                "Harga Jual": sub["sell_idr"].apply(format_rp),
                "Harga Beli": sub["buyback_idr"].apply(format_rp)
            }))
        else:
             st.subheader("📋 Preview Data Terupload")
             st.success("Data di bawah ini sudah tersimpan di Google Drive.")
             st.dataframe(df_active, use_container_width=True)

with tab2:
    st.subheader("📈 Grafik Histori")
    sheet_to_view = st.selectbox("Sumber Data", ["Summary_100g", "Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK_Logam_Mulia", "Agung_Jewellery"])
    df_hist = get_full_history(worksheet_name=sheet_to_view)
    if not df_hist.empty:
        c1, c2 = st.columns(2)
        v_plot = c1.selectbox("Vendor", df_hist['vendor'].unique())
        w_plot = c2.selectbox("Berat", sorted(df_hist['weight_g'].unique()))
        plot_df = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)]
        if not plot_df.empty:
            st.plotly_chart(px.line(plot_df, x="timestamp", y="sell_idr", markers=True, title=f"Tren {v_plot} {w_plot}g"), width='stretch')
