import pandas as pd
import os
from datetime import datetime

# Simpan histori di root agar mudah diakses
HISTORY_FILE = "gold_price_history.csv"

def save_to_history(df_new):
    if df_new.empty:
        return
    
    # Beri label waktu kapan data ini dimasukkan
    df_new['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if os.path.exists(HISTORY_FILE):
        df_old = pd.read_csv(HISTORY_FILE)
        # Gabungkan data lama dan baru
        df_final = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_final = df_new
        
    # Hapus baris yang benar-benar identik agar tidak dobel
    df_final = df_final.drop_duplicates()
    df_final.to_csv(HISTORY_FILE, index=False)

def get_full_history():
    if os.path.exists(HISTORY_FILE):
        return pd.read_csv(HISTORY_FILE)
    return pd.DataFrame()
