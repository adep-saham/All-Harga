import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

def save_to_history(df_new, worksheet_name="Summary_100g"):
    """Menyimpan data ke tab spesifik di Google Sheets dengan info update sumber."""
    if df_new is None or df_new.empty:
        st.error("Data baru kosong, tidak ada yang disimpan.")
        return False
    
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # 1. Definisikan Struktur Kolom (Termasuk source_update)
        cols = ['timestamp', 'vendor', 'weight_g', 'sell_idr', 'buyback_idr', 'source_update']
        
        # 2. Coba baca data lama
        df_old = pd.DataFrame()
        try:
            df_old = conn.read(worksheet=worksheet_name)
        except Exception:
            st.error(f"❌ TAB TIDAK DITEMUKAN: Silakan buat tab bernama '{worksheet_name}' di Google Sheets Anda.")
            return False
        
        # 3. Siapkan data baru
        df_to_save = df_new.copy()
        # Waktu penarikan data (WIB)
        df_to_save['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Sinkronisasi nama vendor jika perlu
        if 'vendor' not in df_to_save.columns and 'Nama Toko Emas' in df_to_save.columns:
            df_to_save['vendor'] = df_to_save['Nama Toko Emas']
            
        # Pastikan kolom source_update ada (jika tidak ada di df_new, beri nilai default)
        if 'source_update' not in df_to_save.columns:
            df_to_save['source_update'] = "N/A"
                
        # Filter dan urutkan kolom
        df_to_save = df_to_save[cols]
        
        # 4. Gabungkan Data (Menangani data kosong)
        if df_old is None or df_old.empty or df_old.dropna(how='all').empty:
            df_final = df_to_save
        else:
            # Pastikan tipe data konsisten agar tidak muncul FutureWarning
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
            df_final = pd.concat([df_old, df_to_save], ignore_index=True)
        
        # 5. Kirim kembali ke Google Sheets
        conn.update(worksheet=worksheet_name, data=df_final)
        return True
        
    except Exception as e:
        st.error(f"Gagal Simpan ke {worksheet_name}: {str(e)}")
        return False

def get_full_history(worksheet_name="Summary_100g"):
    """Mengambil data histori dari tab tertentu."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet=worksheet_name)
        return df if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()
