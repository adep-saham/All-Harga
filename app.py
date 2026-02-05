import re
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup

URL = "https://galeri24.co.id/harga-emas"

def rupiah_to_int(s: str) -> int:
    if s is None:
        return 0
    s = str(s).strip()
    s = s.replace("Rp", "").replace(" ", "").replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0

def parse_update_date(text: str) -> str:
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if not m:
        return datetime.now().strftime("%Y-%m-%d")

    day = int(m.group(1))
    mon_name = m.group(2).lower()
    year = int(m.group(3))
    months = {
        "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
        "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12
    }
    month = months.get(mon_name)
    if not month:
        return datetime.now().strftime("%Y-%m-%d")
    return f"{year:04d}-{month:02d}-{day:02d}"

def scrape_prices(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")

    # Ambil teks dengan newline supaya urutan “tabel” kebaca
    text = soup.get_text("\n", strip=True)
    update_date = parse_update_date(text)

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    def is_weight(x: str) -> bool:
        # weight bisa "0.5", "0,5", "1", "2", "25", "1000"
        x = x.replace(",", ".")
        return bool(re.fullmatch(r"\d+(\.\d+)?", x))

    def is_rp(x: str) -> bool:
        return "Rp" in x

    rows = []
    vendor = None
    i = 0

    while i < len(lines):
        ln = lines[i]

        # start section vendor
        if ln.startswith("Harga "):
            vendor = ln.replace("Harga ", "").strip()
            i += 1
            continue

        # skip header lines
        if ln.lower() in {"berat", "harga jual", "harga buyback"}:
            i += 1
            continue

        # stop/neutral markers
        if ln.startswith("Diperbarui"):
            i += 1
            continue

        # parse triplet: weight, Rp sell, Rp buyback
        if vendor and is_weight(ln):
            w = float(ln.replace(",", "."))
            # cari 2 baris berikutnya yang Rp (kadang ada noise)
            j = i + 1
            rp_vals = []
            while j < len(lines) and len(rp_vals) < 2:
                if is_rp(lines[j]):
                    rp_vals.append(lines[j])
                # stop kalau masuk vendor berikutnya
                if lines[j].startswith("Harga "):
                    break
                j += 1

            if len(rp_vals) == 2:
                sell = rupiah_to_int(rp_vals[0])
                buyback = rupiah_to_int(rp_vals[1])
                rows.append({
                    "date": update_date,
                    "vendor": vendor,
                    "weight_g": w,
                    "sell_idr": sell,
                    "buyback_idr": buyback,
                    "source": URL
                })
                i = j
                continue

        i += 1

    if not rows:
        # Untuk debug: simpan potongan text biar kelihatan struktur di Streamlit logs
        raise RuntimeError(
            "Tidak menemukan data harga. Kemungkinan halaman berubah / diblok.\n"
            "Coba cek apakah HTML berisi kata 'Harga ANTAM' atau 'Harga UBS'."
        )

    df = pd.DataFrame(rows).drop_duplicates(
        subset=["date", "vendor", "weight_g", "sell_idr", "buyback_idr"]
    ).sort_values(["vendor", "weight_g"])

    return df
