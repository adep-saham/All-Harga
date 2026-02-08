import streamlit as st
from scrapers.stargold import parse_stargold
from utils.history_manager import save_to_history

def render_uploader_sidebar():
    st.sidebar.divider()
    st.sidebar.subheader("📥 Update & Simpan Histori")
    
    uploaded_file = st.sidebar.file_uploader(
        "Upload Source Web (TXT)", 
        type=['txt'],
        key="gold_uploader_widget"
    )

    if uploaded_file is not None:
        try:
            content = uploaded_file.getvalue().decode("utf-8")
            
            # Gunakan scraper stargold yang sudah ada untuk ekstrak data
            df_extracted, msg = parse_stargold(content)
            
            if not df_extracted.empty:
                # Simpan ke CSV Histori
                save_to_history(df_extracted)
                st.sidebar.success("✅ Berhasil disimpan ke Histori!")
            else:
                st.sidebar.error("❌ Data tidak ditemukan dalam file.")
        except Exception as e:
            st.sidebar.error(f"❌ Gagal: {e}")
