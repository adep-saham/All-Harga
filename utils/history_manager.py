import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# Masukkan URL Google Sheet Anda di sini atau di Secrets
SHEET_URL = "https://docs.google.com/spreadsheets/d/1hI-pNUNqO2aGuLfIyKuT7zFAI43iKqC19RIKQBtlrck/edit?usp=sharing"

def save_to_history(df_new):
    """Menyimpan data ke Google Sheets (Append)."""
    if df_new.empty:
        return
    
    try:
        # Inisialisasi koneksi
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Ambil data lama
        df_old = conn.read(spreadsheet=SHEET_URL)
        
        # Siapkan data baru dengan timestamp
        df_new_to_save = df_new.copy()
        df_new_to_save['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Pastikan urutan kolom sama
        cols = ['timestamp', 'vendor', 'weight_g', 'sell_idr', 'buyback_idr']
        df_new_to_save = df_new_to_save[cols]
        
        # Gabungkan
        df_final = pd.concat([df_old, df_new_to_save], ignore_index=True)
        
        # Update Google Sheets
        conn.update(spreadsheet=SHEET_URL, data=df_final)
        return True
    except Exception as e:
        st.error(f"Gagal simpan ke Google Sheets: {e}")
        return False

def get_full_history():
    """Mengambil seluruh data dari Google Sheets untuk grafik."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(spreadsheet=SHEET_URL)
        return df
    except Exception:
        return pd.DataFrame()
