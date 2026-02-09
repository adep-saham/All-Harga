import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

def save_to_history(df_new, worksheet_name="Summary_100g"):
    """
    Menyimpan data ke tab spesifik di Google Sheets.
    Menghindari duplikasi jika data yang sama persis sudah ada.
    """
    if df_new is None or df_new.empty:
        st.error("Data baru kosong, tidak ada yang disimpan.")
        return False
    
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 1. Struktur Kolom Standar
        cols = ['timestamp', 'vendor', 'weight_g', 'sell_idr', 'buyback_idr', 'source_update']
        
        # 2. Baca data lama (tanpa cache agar akurat)
        df_old = pd.DataFrame()
        try:
            df_old = conn.read(worksheet=worksheet_name, ttl=0)
        except Exception:
            st.error(f"❌ TAB '{worksheet_name}' tidak ditemukan di Google Sheets.")
            return False
        
        # 3. Siapkan data baru untuk ditambahkan
        df_to_save = df_new.copy()
        df_to_save['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Pastikan kolom source_update ada
        if 'source_update' not in df_to_save.columns:
            df_to_save['source_update'] = "N/A"
            
        # Pilih hanya kolom yang diperlukan
        df_to_save = df_to_save[cols]
        
        # 4. Gabungkan dengan data lama
        if df_old is None or df_old.empty or df_old.dropna(how='all').empty:
            df_final = df_to_save
        else:
            # Samakan tipe data agar penggabungan mulus
            df_old = df_old[cols].astype({
                'weight_g': float, 
                'sell_idr': float, 
                'buyback_idr': float
            })
            df_to_save = df_to_save.astype({
                'weight_g': float, 
                'sell_idr': float, 
                'buyback_idr': float
            })
            
            # Gabungkan (Data baru ditaruh di bawah)
            df_combined = pd.concat([df_old, df_to_save], ignore_index=True)
            
            # Hapus duplikat (opsional: jika vendor, berat, dan harga sama persis)
            df_final = df_combined.drop_duplicates(
                subset=['vendor', 'weight_g', 'sell_idr', 'buyback_idr', 'source_update'], 
                keep='first'
            )
        
        # 5. Update kembali ke Google Sheets
        conn.update(worksheet=worksheet_name, data=df_final)
        return True
        
    except Exception as e:
        st.error(f"Gagal Simpan ke {worksheet_name}: {str(e)}")
        return False

def get_full_history(worksheet_name="Summary_100g"):
    """
    Mengambil seluruh histori dari Google Sheets tanpa cache (ttl=0).
    """
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet=worksheet_name, ttl=0)
        return df
    except:
        return pd.DataFrame()
