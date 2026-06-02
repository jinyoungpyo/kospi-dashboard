"""네이버 금융 KOSPI 일별 시세 수집 (T+0 종가/거래대금 보강용).

FreeSIS 유가증권시장 통계(STATSCU0100000020)는 T+1 발행이라 당일 종가가
다음날 오후에야 들어옴. 네이버는 장 마감 직후 발행하므로 fallback 소스로
사용해 가장 최근 거래일 KOSPI를 즉시 dashboard에 노출.

build_dashboard_data.py가 FreeSIS 우선, 결측일만 네이버로 채우는 방식으로 머지.
페이지가 1회 호출에 10거래일 반환 → page=1 한 번이면 보강 충분.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
URL = "https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page=1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://finance.naver.com/",
}
DATE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


def main() -> None:
    sess = requests.Session()
    sess.headers.update(HEADERS)
    r = sess.get(URL, timeout=15)
    r.encoding = "euc-kr"
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.select_one("table.type_1")
    if table is None:
        print("[!] table not found")
        return

    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        cells = [t.get_text(strip=True).replace(",", "") for t in tds]
        # 6컬럼: 날짜, 체결가, 전일비, 등락률, 거래량(천주), 거래대금(백만원)
        if len(cells) < 6 or not DATE_RE.match(cells[0]):
            continue
        try:
            close = float(cells[1])
            value = int(cells[5])  # 백만원
        except ValueError:
            continue
        out.append({
            "date": cells[0].replace(".", "-"),
            "KOSPI지수": close,
            "거래대금": value,
        })

    if not out:
        print("[!] no rows parsed")
        return

    df = pd.DataFrame(out).sort_values("date").reset_index(drop=True)
    csv_path = DATA / "naver_kospi_daily.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[+] saved {len(df)} rows: {csv_path}")
    print(df.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
