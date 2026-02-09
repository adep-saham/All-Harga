import streamlit as st
import os
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
            # 1. Baca isi file yang di-upload
            content = uploaded_file.getvalue().decode("utf-8")
            
            # 2. SIMPAN FILE KE SERVER (Penting agar Realtime Update)
            # Kita simpan sebagai 'source web.txt' agar terbaca oleh scraper stargold
            with open("source web.txt", "w", encoding="utf-8") as f:
                f.write(content)
            
            # 3. Ekstrak data menggunakan scraper stargold
            df_extracted, msg = parse_stargold(content)
            
            if not df_extracted.empty:
                # 4. Simpan ke Google Sheets (Histori)
                # Secara default akan masuk ke tab 'Summary_100g'
                if save_to_history(df_extracted, worksheet_name="Summary_100g"):
                    st.sidebar.success("✅ File disimpan di server & data dicatat di Histori!")
                    
                    # 5. BERSIHKAN CACHE (Agar tampilan aplikasi langsung berubah)
                    st.cache_data.clear()
                else:
                    st.sidebar.warning("⚠️ File disimpan di server, tapi gagal catat di Google Sheets.")
            else:
                st.sidebar.error("❌ Data tidak ditemukan dalam file. Cek isi TXT Anda.")
                
        except Exception as e:
            st.sidebar.error(f"❌ Gagal: {e}")
