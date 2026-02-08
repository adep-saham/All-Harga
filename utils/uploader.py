import streamlit as st
from scrapers.stargold import parse_stargold
from utils.history_manager import save_to_history

def render_uploader_sidebar():
    st.sidebar.markdown("---")
    st.sidebar.subheader("📥 Update Harga Baru")
    
    # Widget Upload
    uploaded_file = st.sidebar.file_uploader(
        "Upload Source Web (TXT)", 
        type=['txt'],
        key="main_gold_uploader"
    )

    if uploaded_file is not None:
        try:
            # Baca isi file
            content = uploaded_file.getvalue().decode("utf-8")
            
            # Jalankan scraper untuk ekstrak data dari konten yang di-upload
            df_extracted, msg = parse_stargold(content)
            
            if not df_extracted.empty:
                # Simpan ke histori
                save_to_history(df_extracted)
                st.sidebar.success("✅ Berhasil disimpan ke histori!")
                # Beri info data apa saja yang masuk
                st.sidebar.caption(f"Terdeteksi {len(df_extracted)} baris harga.")
            else:
                st.sidebar.error("❌ File terbaca, tapi format harga tidak cocok.")
        except Exception as e:
            st.sidebar.error(f"❌ Gagal memproses: {e}")
