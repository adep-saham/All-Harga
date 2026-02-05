import re
from datetime import datetime
import requests
import pandas as pd
from bs4 import BeautifulSoup

URL = "https://galeri24.co.id/harga-emas"


def rupiah_to_int(s: str) -> int:
    """Convert 'Rp1.560.000' -> 1560000"""
    if s is None:
        return 0
    s = str(s).strip()
    s = s.replace("Rp", "").replace(" ", "").replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0


def parse_update_date(text: str) -> str:
    """
    Extract Indonesian date like 'Diperbarui Kamis, 5 Februari 2026' -> '2026-02-05'
    Fallback: today
    """
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


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def scrape_prices(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")

    # Ambil teks seluruh halaman untuk cari "Diperbarui ..."
    page_text = soup.get_text(" ", strip=True)
    update_date = parse_update_date(page_text)

    rows = []
    # Cari heading yang diawali "Harga " lalu ambil tabel setelahnya
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "div", "span"]):
        title = (el.get_text(" ", strip=True) or "").strip()
        if not title.startswith("Harga "):
            continue

        vendor = title.replace("Harga ", "").strip()
        table = el.find_next("table")
        if table is None:
            continue

        for tr in table.find_all("tr"):
            cols = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if len(cols) < 3:
                continue
            if cols[0].lower() in {"berat", "weight"}:
                continue

            # Berat biasanya "0,5" atau "1" dst
            w_raw = cols[0].replace(",", ".")
            try:
                weight_g = float(w_raw)
            except ValueError:
                continue

            sell = rupiah_to_int(cols[1])
            buyback = rupiah_to_int(cols[2])

            rows.append({
                "date": update_date,
                "vendor": vendor,
                "weight_g": weight_g,
                "sell_idr": sell,
                "buyback_idr": buyback,
                "source": URL
            })

    if not rows:
        raise RuntimeError("Tidak menemukan tabel harga. Struktur halaman mungkin berubah.")

    df = pd.DataFrame(rows).drop_duplicates(
        subset=["date", "vendor", "weight_g", "sell_idr", "buyback_idr"]
    ).sort_values(["vendor", "weight_g"])

    return df


def main():
    html = fetch_html(URL)
    df = scrape_prices(html)

    # tampilkan preview
    print(df.head(30).to_string(index=False))

    # simpan file lokal
    today = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"galeri24_harga_emas_{today}.csv"
    xlsx_path = f"galeri24_harga_emas_{today}.xlsx"

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)

    print(f"\n✅ Saved:\n- {csv_path}\n- {xlsx_path}")


if __name__ == "__main__":
    main()
