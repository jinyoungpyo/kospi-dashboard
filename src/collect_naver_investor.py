"""네이버 금융 '투자자별 매매동향' KOSPI 외국인 순매수 수집.

페이지: https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate=YYYYMMDD
한 호출에 bizdate 포함 이전 10거래일 표시. 유가증권시장 CSV의 거래일을
10일 stride로 샘플링해 호출, 중복 제거.

테이블 컬럼 (11개, td):
  [0] 날짜  [1] 개인  [2] 외국인 ← 채집 대상  [3] 기관계
  [4]~[9] 기관 세부  [10] 기타법인
단위: 억원
"""
from __future__ import annotations

import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
URL = "https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={d}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://finance.naver.com/",
}

DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{2}")


def fetch_one(bizdate: str, sess: requests.Session) -> list[dict]:
    r = sess.get(URL.format(d=bizdate), timeout=15)
    r.encoding = "euc-kr"
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.select_one("table.type_1")
    out = []
    if table is None:
        return out
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) != 11:
            continue
        cells = [td.get_text(strip=True).replace(",", "") for td in tds]
        if not DATE_RE.match(cells[0]):
            continue
        try:
            foreign = int(cells[1 + 1])  # cell[2] = 외국인
        except ValueError:
            continue
        yy, mm, dd = cells[0].split(".")
        out.append({"date": f"20{yy}-{mm}-{dd}", "외국인_순매수_억": foreign})
    return out


def main() -> None:
    idx = pd.read_csv(DATA / "유가증권시장_2026Q1Q2.csv")
    dates = pd.to_datetime(idx["date"]).dt.strftime("%Y%m%d").tolist()

    # 최신부터 stride 10 으로 샘플링 (페이지가 10일씩 반환하므로)
    sample_idx = list(range(len(dates) - 1, -1, -10))
    if sample_idx[-1] != 0:
        sample_idx.append(0)
    sample_bizdates = [dates[i] for i in sample_idx]

    # KOSPI(FreeSIS) CSV는 T+1 발행 지연이 있어 사용자 측면에선 최신 거래일이
    # 빠지는 일이 잦음. 오늘 날짜로 한 번 더 쿼리해 그날 포함 ~10거래일을 보강.
    today_str = date.today().strftime("%Y%m%d")
    if today_str not in sample_bizdates:
        sample_bizdates.insert(0, today_str)

    sess = requests.Session()
    sess.headers.update(HEADERS)

    seen: set[str] = set()
    all_rows: list[dict] = []
    for biz in sample_bizdates:
        try:
            rows = fetch_one(biz, sess)
            new_rows = [r for r in rows if r["date"] not in seen]
            for r in new_rows:
                seen.add(r["date"])
            all_rows.extend(new_rows)
            print(f"  bizdate={biz}: fetched {len(rows)}  new {len(new_rows)}")
        except Exception as e:
            print(f"  {biz}: ERR {e}")
        time.sleep(0.3)

    if not all_rows:
        print("[!] no data collected")
        return

    df = pd.DataFrame(all_rows).sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    out = DATA / "외국인_순매수_2026Q1Q2.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n[+] saved: {out}  unique dates: {len(df)}")
    print(df.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
