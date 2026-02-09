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
        # Tambahkan tombol agar tidak otomatis simpan setiap kali app di-refresh
        if st.sidebar.button("💾 Proses & Simpan StarGold", use_container_width=True):
            try:
                content = uploaded_file.getvalue().decode("utf-8")
                
                # Ekstrak data
                df_extracted, msg = parse_stargold(content)
                
                if not df_extracted.empty:
                    # Simpan ke Google Sheets (Tab StarGold atau Summary sesuai logika manager)
                    # Kita arahkan ke tab StarGold agar lebih spesifik
                    if save_to_history(df_extracted, worksheet_name="StarGold"):
                        st.sidebar.success("✅ Data StarGold Berhasil disimpan!")
                        # Hapus cache agar tampilan utama berubah
                        st.cache_data.clear()
                    else:
                        st.sidebar.error("❌ Gagal menyimpan ke Google Sheets.")
                else:
                    st.sidebar.error("❌ Data tidak ditemukan dalam file.")
            except Exception as e:
                st.sidebar.error(f"❌ Gagal: {e}")
