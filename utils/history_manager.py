import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

def save_to_history(df_new, worksheet_name="Summary_100g"):
    """
    Fungsi dasar untuk menyimpan data ke tab tertentu di Google Sheets.
    Jika tab belum ada, sistem akan mencoba membuatnya (tergantung izin service account).
    """
    if df_new is None or df_new.empty:
        return False
    
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Struktur kolom standar untuk database histori
        cols = ['timestamp', 'vendor', 'weight_g', 'sell_idr', 'buyback_idr', 'source_update']
        
        # 1. Baca data lama (ttl=0 untuk memastikan data paling segar)
        df_old = pd.DataFrame()
        try:
            df_old = conn.read(worksheet=worksheet_name, ttl=0)
        except Exception:
            # Jika tab tidak ditemukan, kita mulai dengan DataFrame kosong ber-header
            df_old = pd.DataFrame(columns=cols)
        
        # 2. Siapkan data baru
        df_to_save = df_new.copy()
        df_to_save['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Pastikan kolom source_update tersedia
        if 'source_update' not in df_to_save.columns:
            df_to_save['source_update'] = "N/A"
            
        # Ambil hanya kolom yang sesuai urutan
        df_to_save = df_to_save[cols]
        
        # 3. Gabungkan dan Hapus Duplikat (agar data tidak menumpuk jika diklik berkali-kali)
        if df_old.empty or df_old.dropna(how='all').empty:
            df_final = df_to_save
        else:
            # Samakan tipe data agar penggabungan tidak error
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
            
            df_combined = pd.concat([df_old, df_to_save], ignore_index=True)
            # Hapus duplikat berdasarkan konten (vendor, berat, harga, dan label update sumber)
            df_final = df_combined.drop_duplicates(
                subset=['vendor', 'weight_g', 'sell_idr', 'buyback_idr', 'source_update'], 
                keep='first'
            )
        
        # 4. Kirim kembali ke Google Sheets
        conn.update(worksheet=worksheet_name, data=df_final)
        return True
        
    except Exception as e:
        st.error(f"Gagal simpan ke tab '{worksheet_name}': {e}")
        return False

def save_batch_to_history(df_all):
    """
    Fungsi 'Sekali Klik' untuk menyimpan ke tiga tujuan sekaligus:
    1. Tab Summary_100g (Hanya pecahan 100g dari semua vendor)
    2. Tab Vendor (Seluruh pecahan ke tab masing-masing vendor)
    3. Tab Log Harian (Seluruh data tarikan ke tab khusus tanggal hari ini)
    """
    if df_all is None or df_all.empty:
        st.error("Tidak ada data untuk disimpan masal.")
        return False
        
    try:
        success_count = 0
        
        # A. SIMPAN KE SUMMARY 100G
        df_100 = df_all[df_all['weight_g'] == 100].copy()
        if not df_100.empty:
            if save_to_history(df_100, "Summary_100g"):
                success_count += 1
        
        # B. SIMPAN KE DETAIL VENDOR (Tab masing-masing)
        for v_name in df_all['vendor'].unique():
            df_v = df_all[df_all['vendor'] == v_name].copy()
            tab_name = v_name.replace(" ", "_") # Ganti spasi dengan underscore untuk nama tab
            if save_to_history(df_v, tab_name):
                pass # Berhasil simpan detail vendor
        
        # C. SIMPAN KE LOG HARIAN (Tab per Hari)
        # Nama tab otomatis: Log_09Feb26
        daily_tab_name = f"Log_{datetime.now().strftime('%d%b%y')}"
        if save_to_history(df_all, daily_tab_name):
            success_count += 1
            
        return success_count > 0
    except Exception as e:
        st.error(f"Error pada sistem Batch Save: {e}")
        return False

def get_full_history(worksheet_name="Summary_100g"):
    """
    Mengambil data histori tanpa cache (ttl=0) agar grafik selalu realtime.
    """
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read(worksheet=worksheet_name, ttl=0)
    except Exception:
        return pd.DataFrame()
