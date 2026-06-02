"""4개 CSV를 단일 JSON(dashboard/assets/data.json)으로 통합. 차트용 미니 데이터셋."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT  = ROOT / "dashboard" / "assets"
OUT.mkdir(parents=True, exist_ok=True)


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def main() -> None:
    jeungsi = load(DATA / "jeungsi_jageum_2026Q1Q2.csv")[
        ["date", "투자자예탁금", "장내파생상품_예수금", "RP_매도잔고"]
    ]
    jeungsi = jeungsi.rename(
        columns={"장내파생상품_예수금": "파생예수금", "RP_매도잔고": "RP매도잔고"}
    )
    credit  = load(DATA / "신용공여_잔고_2026Q1Q2.csv")[
        ["date", "신용거래융자_전체", "예탁증권담보융자"]
    ]
    credit  = credit.rename(
        columns={"신용거래융자_전체": "신용잔고", "예탁증권담보융자": "증권담보융자"}
    )
    lending = load(DATA / "대차거래_추이_2026Q1Q2.csv")[["date", "잔고_금액"]]
    lending = lending.rename(columns={"잔고_금액": "대차잔고"})
    kospi   = load(DATA / "유가증권시장_2026Q1Q2.csv")[
        ["date", "KOSPI지수", "거래대금", "시가총액", "외국인_비중_pct"]
    ]

    # FreeSIS는 T+1 발행이라 당일 KOSPI/거래대금이 누락됨.
    # 네이버 finance(T+0)로 결측만 보강 — FreeSIS 값이 있으면 그쪽 우선.
    naver_kospi_path = DATA / "naver_kospi_daily.csv"
    if naver_kospi_path.exists():
        naver_k = load(naver_kospi_path)[["date", "KOSPI지수", "거래대금"]]
        kospi = kospi.merge(naver_k, on="date", how="outer", suffixes=("", "_naver"))
        kospi["KOSPI지수"] = kospi["KOSPI지수"].fillna(kospi["KOSPI지수_naver"])
        kospi["거래대금"]   = kospi["거래대금"].fillna(kospi["거래대금_naver"])
        kospi = kospi.drop(columns=["KOSPI지수_naver", "거래대금_naver"])
        kospi = kospi.sort_values("date").reset_index(drop=True)

    foreign_path = DATA / "외국인_순매수_2026Q1Q2.csv"
    foreign = load(foreign_path)[["date", "외국인_순매수_억"]] if foreign_path.exists() else None

    # outer join: 지표마다 발행 시각이 달라 가장 최근 일자가 다를 수 있음.
    # KOSPI 기준 left join이면 KOSPI 미발행 시 다른 지표의 최신값이 모두 누락됨.
    df = kospi.merge(jeungsi, on="date", how="outer") \
              .merge(credit, on="date", how="outer") \
              .merge(lending, on="date", how="outer")
    if foreign is not None:
        df = df.merge(foreign, on="date", how="outer")
    df = df.sort_values("date").reset_index(drop=True)

    df["신용_시총비율_pct"] = (df["신용잔고"] / df["시가총액"] * 100).round(3)

    out = {
        "range": {"start": df["date"].min(), "end": df["date"].max()},
        "rows": json.loads(df.to_json(orient="records")),
    }
    (OUT / "data.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(f"[+] rows: {len(df)}  cols: {list(df.columns)}")
    print(f"[+] saved: {OUT / 'data.json'}")
    print(df.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
