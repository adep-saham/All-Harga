import requests
from bs4 import BeautifulSoup
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re

# ======================
# CONFIG
# ======================
URL = "https://galeri24.co.id/harga-emas"
SPREADSHEET_NAME = "Harga Emas Harian"
SHEET_NAME = "GALERI24"
CREDENTIALS_FILE = "credentials.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# ======================
# UTIL
# ======================
def clean_price(text):
    if not text:
        return None
    return int(re.sub(r"[^\d]", "", text))

# ======================
# SCRAPER
# ======================
def scrape_galeri24():
    res = requests.get(URL, headers=HEADERS, timeout=20)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    table = soup.find("table")
    rows = table.find("tbody").find_all("tr")

    data = []
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 3:
            continue

        data.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "Galeri 24",
            "berat": cols[0],
            "harga_jual": clean_price(cols[1]),
            "harga_buyback": clean_price(cols[2]),
            "sumber": URL
        })

    return pd.DataFrame(data)

# ======================
# GOOGLE SHEET
# ======================
def save_to_gsheet(df):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=scopes
    )

    client = gspread.authorize(creds)

    sh = client.open(SPREADSHEET_NAME)

    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_NAME, rows="100", cols="20")
        ws.append_row(df.columns.tolist())

    # append data
    ws.append_rows(df.values.tolist(), value_input_option="USER_ENTERED")

# ======================
# MAIN
# ======================
if __name__ == "__main__":
    df = scrape_galeri24()
    save_to_gsheet(df)

    print("✅ Data harga emas Galeri 24 berhasil disimpan ke Google Sheet")
