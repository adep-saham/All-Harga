import streamlit as st
import os
from scrapers.stargold import parse_stargold
from utils.history_manager import save_to_history

def render_uploader_sidebar():
    st.sidebar.divider()
    st.sidebar.subheader("📥 Update & Simpan Histori")
    
    # Komponen upload file
    uploaded_file = st.sidebar.file_uploader(
        "Upload Source Web (TXT)", 
        type=['txt'],
        key="gold_uploader_widget"
    )

    if uploaded_file is not None:
        # Menambahkan tombol konfirmasi agar tidak terjadi 'auto-save' yang berulang
        if st.sidebar.button("💾 Proses & Simpan StarGold", use_container_width=True):
            try:
                # 1. Baca isi file yang di-upload
                content = uploaded_file.getvalue().decode("utf-8")
                filename = uploaded_file.name
                
                # 2. SIMPAN FILE KE SERVER (Kunci sinkronisasi)
                # Kita simpan dengan nama aslinya agar glob.glob di stargold.py menemukannya
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                
                # Kita juga timpa ke 'source web.txt' sebagai standar utama
                with open("source web.txt", "w", encoding="utf-8") as f:
                    f.write(content)
                
                # 3. Ekstrak data menggunakan scraper stargold
                # Kita kirim 'content' langsung agar proses lebih cepat
                df_extracted, msg = parse_stargold(content)
                
                if not df_extracted.empty:
                    # 4. Simpan ke Google Sheets (Tab StarGold)
                    if save_to_history(df_extracted, worksheet_name="StarGold"):
                        st.sidebar.success(f"✅ Berhasil! File '{filename}' disimpan & Histori dicatat.")
                        
                        # 5. BERSIHKAN CACHE
                        # Ini memaksa app.py untuk menarik data baru dari file yang baru kita simpan
                        st.cache_data.clear()
                    else:
                        st.sidebar.error("❌ Gagal mencatat ke Google Sheets. Periksa koneksi internet.")
                else:
                    st.sidebar.error("❌ Data tidak ditemukan. Pastikan isi file TXT benar.")
                    
            except Exception as e:
                st.sidebar.error(f"❌ Gagal memproses file: {e}")
