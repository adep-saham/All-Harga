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
        cols = ['timestamp', 'vendor', 'weight_g', 'sell_idr', 'buyback_idr', 'source_update']
        
        df_old = pd.DataFrame()
        try:
            df_old = conn.read(worksheet=worksheet_name, ttl=0)
        except Exception:
            df_old = pd.DataFrame(columns=cols)
        
        df_to_save = df_new.copy()
        df_to_save['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if 'source_update' not in df_to_save.columns:
            df_to_save['source_update'] = "N/A"
            
        df_to_save = df_to_save[cols]
        
        if df_old.empty or df_old.dropna(how='all').empty:
            df_final = df_to_save
        else:
            df_old = df_old[cols].astype({'weight_g': float, 'sell_idr': float, 'buyback_idr': float})
            df_to_save = df_to_save.astype({'weight_g': float, 'sell_idr': float, 'buyback_idr': float})
            df_combined = pd.concat([df_old, df_to_save], ignore_index=True)
            df_final = df_combined.drop_duplicates(
                subset=['vendor', 'weight_g', 'sell_idr', 'buyback_idr', 'source_update'], 
                keep='first'
            )
        
        conn.update(worksheet=worksheet_name, data=df_final)
        return True
    except Exception as e:
        st.error(f"Gagal simpan ke tab '{worksheet_name}': {e}")
        return False

def save_batch_to_history(df_all):
    """Fungsi sekali klik untuk simpan ke Summary, Vendor, dan Log Harian."""
    if df_all is None or df_all.empty:
        return False
    try:
        success = False
        # 1. Simpan ke Summary 100g
        df_100 = df_all[df_all['weight_g'] == 100].copy()
        if not df_100.empty:
            if save_to_history(df_100, "Summary_100g"): success = True
        
        # 2. Simpan ke Detail Vendor masing-masing
        for v_name in df_all['vendor'].unique():
            df_v = df_all[df_all['vendor'] == v_name].copy()
            if save_to_history(df_v, v_name.replace(" ", "_")): success = True
        
        # 3. Simpan ke Log Harian
        daily_tab = f"Log_{datetime.now().strftime('%d%b%y')}"
        if save_to_history(df_all, daily_tab): success = True
            
        return success
    except:
        return False

def get_full_history(worksheet_name="Summary_100g"):
    """Mengambil data histori tanpa cache (realtime)."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read(worksheet=worksheet_name, ttl=0)
    except:
        return pd.DataFrame()
