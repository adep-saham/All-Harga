import pandas as pd
import requests
import re
from io import BytesIO
from typing import Tuple

CID = "7181a7df3eab3581"
RESID = f"{CID.upper()}!106"
AUTHKEY = "IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8"

# 🔥 FIX UTAMA: pakai download.aspx + export
URL_HAKABEGOLD = (
    "https://onedrive.live.com/download.aspx"
    f"?resid={RESID}"
    f"&authkey={AUTHKEY}"
    "&export=download"
)

def parse_hakabegold() -> Tuple[pd.DataFrame, str]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
            "Referer": "https://onedrive.live.com/",
        }

        r = requests.get(URL_HAKABEGOLD, headers=headers, timeout=60)

        if r.status_code != 200:
            return pd.DataFrame(), f"Gagal Koneksi (Code: {r.status_code})"

        if "text/html" in r.headers.get("Content-Type", "").lower():
            return pd.DataFrame(), "Link mengarah ke HTML (authkey/resid salah)"

        xls = pd.read_excel(BytesIO(r.content), sheet_name=None, header=None)

        final_df = pd.DataFrame()
        label = "HK Logam Mulia"

        for _, df in xls.items():
            for i, row in df.head(40).iterrows():
                text = " ".join(row.astype(str).lower())
                if ("berat" in text or "gram" in text) and ("jual" in text or "user" in text):
                    df.columns = df.iloc[i].astype(str).str.lower()
                    data = df.iloc[i + 1:].copy()

                    c_berat = next((c for c in df.columns if "berat" in c or "gram" in c), None)
                    c_jual = next((c for c in df.columns if "jual" in c or "user" in c or "harga" in c), None)

                    if not c_berat or not c_jual:
                        continue

                    data["weight_g"] = data[c_berat].apply(_clean_float)
                    data["sell_idr"] = data[c_jual].apply(_clean_int)
                    data["stock"] = "Ready"

                    valid = data[(data["weight_g"] > 0) & (data["sell_idr"] > 0)].copy()

                    if not valid.empty:
                        valid["vendor"] = "HK Logam Mulia"
                        valid["buyback_idr"] = 0
                        final_df = valid[["vendor", "weight_g", "sell_idr", "buyback_idr", "stock"]]
                        break
            if not final_df.empty:
                break

        if final_df.empty:
            return pd.DataFrame(), "File terbaca tapi tabel harga tidak dikenali"

        return final_df.sort_values("weight_g"), label

    except Exception as e:
        return pd.DataFrame(), f"Error: {str(e)}"

def _clean_int(v):
    try:
        s = re.sub(r"[^\d]", "", str(v))
        return int(s) if s else 0
    except:
        return 0

def _clean_float(v):
    try:
        s = str(v).lower().replace(",", ".")
        m = re.findall(r"\d+\.?\d*", s)
        return float(m[0]) if m else 0
    except:
        return 0
