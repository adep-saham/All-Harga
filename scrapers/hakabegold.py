import pandas as pd
import requests
from io import BytesIO

HAKABEGOLD_XLSX_URL = (
    "https://1drv.ms/x/c/7181a7df3eab3581/"
    "IQCc7C0BKmBcRoZssWoz1d7kASQwm6IdF1Db4x7FfApW9PE?download=1"
)

def parse_hakabegold():
    r = requests.get(HAKABEGOLD_XLSX_URL, timeout=30)
    r.raise_for_status()

    df_raw = pd.read_excel(BytesIO(r.content))

    # asumsi struktur tabel sesuai screenshot
    df = df_raw.rename(columns={
        "Berat": "weight_g",
        "Harga End User": "sell_idr",
        "Harga End User/gr": "sell_per_g",
        "Harga+PPH 22": "sell_pph",
        "Harga+PPH 22/gr": "sell_pph_per_g",
        "Stok": "stock",
    })

    df["vendor"] = "HK Logam Mulia"
    df["buyback_idr"] = None  # buyback biasanya di baris bawah

    return df, "HK Logam Mulia — via OneDrive XLSX (public)"
