import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

def save_to_history(df_new, worksheet_name="Summary_100g"):
    """Menyimpan data ke tab spesifik di Google Sheets."""
    if df_new is None or df_new.empty:
        return False
    
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 1. Coba baca data lama dari tab spesifik
        try:
            # Menggunakan parameter worksheet untuk memilih tab
            df_old = conn.read(worksheet=worksheet_name)
        except:
            # Jika tab belum ada atau kosong, buat dataframe kosong
            df_old = pd.DataFrame(columns=['timestamp', 'vendor', 'weight_g', 'sell_idr', 'buyback_idr'])
        
        # 2. Siapkan data baru
        df_to_save = df_new.copy()
        df_to_save['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if 'vendor' not in df_to_save.columns and 'Nama Toko Emas' in df_to_save.columns:
            df_to_save['vendor'] = df_to_save['Nama Toko Emas']
            
        cols = ['timestamp', 'vendor', 'weight_g', 'sell_idr', 'buyback_idr']
        df_to_save = df_to_save[cols]
        
        # 3. Gabungkan
        df_final = pd.concat([df_old, df_to_save], ignore_index=True)
        
        # 4. Update ke tab yang dipilih
        conn.update(worksheet=worksheet_name, data=df_final)
        return True
    except Exception as e:
        st.error(f"Gagal Simpan ke {worksheet_name}: {e}")
        return False

def get_full_history(worksheet_name="Summary_100g"):
    """Mengambil data dari tab spesifik untuk grafik."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read(worksheet=worksheet_name)
    except:
        return pd.DataFrame()
