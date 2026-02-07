import re
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.indogold.id"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}

def _idr(text: str | None) -> int | None:
    if not text:
        return None
    val = re.sub(r"[^\d]", "", text)
    return int(val) if val else None

def _weight_gram(name: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*Gram", name, re.I)
    return float(m.group(1)) if m else None

def get_indogold_prices() -> list[dict]:
    """
    Output standar All Harga Emas
    """
    url = f"{BASE_URL}/detail-emas-batangan"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # ambil last update (jika ada)
    last_update = None
    for l in lines:
        if "Last Update" in l:
            last_update = l.replace("Last Update :", "").strip()
            break

    data = []
    i = 0
    while i < len(lines):
        if lines[i].lower() == "nama":
            product = lines[i + 1]

            buy_price = None
            sell_price = None

            for j in range(i, min(i + 15, len(lines))):
                if lines[j].lower() == "harga beli":
                    buy_price = _idr(lines[j + 1])
                if lines[j].lower() == "harga jual":
                    sell_price = _idr(lines[j + 1])

            if buy_price or sell_price:
                data.append({
                    "vendor": "indogold",
                    "brand": product.split()[0],
                    "product_name": product,
                    "weight_g": _weight_gram(product),
                    "buy_price_idr": buy_price,
                    "sell_price_idr": sell_price,
                    "last_update": last_update,
                    "source": url
                })
        i += 1

    return data
