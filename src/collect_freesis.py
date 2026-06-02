"""FreeSIS 다중 서비스 수집기.

각 SERVICE_ID에 대해:
1) Playwright로 페이지를 띄워 thead 텍스트 추출 → TMPV* 매핑 생성
2) AJAX endpoint로 데이터를 받아 매핑 적용
3) CSV 저장

종목별이 아닌 시장 전체 시계열만 대상으로 함.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://freesis.kofia.or.kr"
DATA_URL = f"{BASE}/meta/getMetaDataList.do"
HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "Referer": BASE + "/",
    "Origin": BASE,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
    ),
}

OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(exist_ok=True)

SERVICES = {
    "jeungsi_jageum": {
        "id": "STATSCU0100000060",
        "label": "jeungsi_jageum",
        # 증시자금추이: 날짜 + 투자자예탁금 + 장내파생상품예수금 + RP매도잔고
        # + 위탁매매미수금 + 반대매매금액 + 반대매매비중
        "columns": [
            "date",
            "투자자예탁금",
            "장내파생상품_예수금",
            "RP_매도잔고",
            "위탁매매_미수금",
            "반대매매_금액",
            "반대매매_비중_pct",
        ],
    },
    "credit_balance": {
        "id": "STATSCU0100000070",
        "label": "신용공여_잔고",
        # 화면 컬럼 구조 (백만원): 날짜 + 신용거래융자{전체,유가증권,코스닥}
        # + 신용거래대주{전체,유가증권,코스닥} + 청약자금대출 + 예탁증권담보융자
        "columns": [
            "date",
            "신용거래융자_전체",
            "신용거래융자_유가증권",
            "신용거래융자_코스닥",
            "신용거래대주_전체",
            "신용거래대주_유가증권",
            "신용거래대주_코스닥",
            "청약자금대출",
            "예탁증권담보융자",
        ],
    },
    "lending_balance": {
        "id": "STATSCU0100000140",
        "label": "대차거래_추이",
        # 화면 컬럼: 날짜 + (종목필터 '전체') + 체결주수 + 상환주수 + 잔고주수 + 잔고금액
        "columns": [
            "date",
            "종목",  # 항상 '전체'
            "체결_주수",
            "상환_주수",
            "잔고_주수",
            "잔고_금액",
        ],
    },
    "kospi_market": {
        "id": "STATSCU0100000020",
        "label": "유가증권시장",
        # 화면 컬럼: 날짜 + KOSPI지수 + 거래량 + 거래대금 + 시가총액 + 외국인시가총액 + 외국인비중
        "columns": [
            "date",
            "KOSPI지수",
            "거래량",
            "거래대금",
            "시가총액",
            "외국인_시가총액",
            "외국인_비중_pct",
        ],
    },
}


def fetch_data(service_id: str, start: date, end: date,
               sess: requests.Session) -> pd.DataFrame:
    obj_nm = f"{service_id}BO"
    payload = {
        "dmSearch": {
            "tmpV40": "1000000",
            "tmpV41": "1",
            "tmpV1": "D",
            "tmpV45": start.strftime("%Y%m%d"),
            "tmpV46": end.strftime("%Y%m%d"),
            "OBJ_NM": obj_nm,
        }
    }
    r = sess.post(DATA_URL, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    rows = r.json().get("ds1", [])
    return pd.DataFrame(rows)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(BASE + "/", timeout=30)
    return s


def main() -> None:
    start = date(2026, 1, 2)
    end = date.today()
    sess = make_session()

    for key, info in SERVICES.items():
        sid = info["id"]
        label = info["label"]
        cols = info["columns"]
        print(f"\n=== {label} ({sid}) ===")

        df = fetch_data(sid, start, end, sess)
        print(f"  rows: {len(df)}  cols: {list(df.columns)}")

        tmp_cols = sorted(
            [c for c in df.columns if re.fullmatch(r"TMPV\d+", c)],
            key=lambda x: int(x[4:]),
        )
        assert len(tmp_cols) == len(cols), (
            f"{label}: TMPV column count {len(tmp_cols)} != expected {len(cols)}"
        )
        rename = dict(zip(tmp_cols, cols))
        df_out = df.rename(columns=rename).copy()

        df_out["date"] = pd.to_datetime(df_out["date"], format="%Y%m%d", errors="coerce")
        # 합계/평균 등 날짜 없는 요약행 제거
        df_out = df_out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

        # 항상 동일한 값('전체' 등) 컬럼 제거
        for c in list(df_out.columns):
            if c != "date" and df_out[c].nunique(dropna=False) == 1 and df_out[c].dtype == object:
                df_out = df_out.drop(columns=[c])

        csv_path = OUT / f"{label}_2026Q1Q2.csv"
        df_out.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"  saved: {csv_path}  cols: {list(df_out.columns)}")


if __name__ == "__main__":
    main()
