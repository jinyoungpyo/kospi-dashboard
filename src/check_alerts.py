"""전일 대비 5개 알림 조건을 평가해 GitHub Actions outputs로 전달.

조건 (OR, 하나라도 트리거 시 메일 발송):
- KOSPI 지수: −10% 이상 하락
- 투자자예탁금: −10% 이상 감소
- 거래대금: −10% 이상 감소
- 신용잔고: +10% 이상 증가
- 대차잔고: +10% 이상 증가

출력:
- send (true/false)
- title (메일 제목 일부)
- body  (메일 본문 — 트리거된 항목 리스트)
- date_str (오늘 데이터 날짜)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA_JSON = ROOT / "dashboard" / "assets" / "data.json"
SITE_URL = os.environ.get("SITE_URL", "https://kospi-analysis.pages.dev/")

# (필드명, 임계값 %, 방향: 'down' 하락이면 트리거, 'up' 상승이면 트리거, 라벨)
RULES = [
    ("KOSPI지수",     -10.0, "down", "KOSPI 지수"),
    ("투자자예탁금",   -10.0, "down", "예탁금"),
    ("거래대금",       -10.0, "down", "거래대금"),
    ("신용잔고",       10.0,  "up",   "신용잔고"),
    ("대차잔고",       10.0,  "up",   "대차잔고"),
]


def write_output(key: str, value: str) -> None:
    """GitHub Actions outputs 또는 stdout으로 출력."""
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            if "\n" in value:
                f.write(f"{key}<<EOF\n{value}\nEOF\n")
            else:
                f.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def fmt_value(field: str, v: float) -> str:
    if field == "KOSPI지수":
        return f"{v:,.2f}"
    return f"{v:,.0f}"


def main() -> int:
    if not DATA_JSON.exists():
        print(f"ERROR: {DATA_JSON} not found", file=sys.stderr)
        write_output("send", "false")
        return 1

    data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    if len(rows) < 2:
        print("ERROR: need at least 2 rows", file=sys.stderr)
        write_output("send", "false")
        return 1

    last, prev = rows[-1], rows[-2]
    triggers: list[tuple[str, float, float, float]] = []  # (label, prev_v, last_v, pct)

    for field, threshold, direction, label in RULES:
        if last.get(field) is None or prev.get(field) is None or prev.get(field) == 0:
            continue
        pct = (last[field] - prev[field]) / prev[field] * 100
        if direction == "down" and pct <= threshold:
            triggers.append((label, prev[field], last[field], pct))
        elif direction == "up" and pct >= threshold:
            triggers.append((label, prev[field], last[field], pct))

    if not triggers:
        print(f"[알림 없음] {last['date']} 기준 전일 대비 모든 지표 정상 범위")
        write_output("send", "false")
        return 0

    # 제목: "예탁금 -12.3% / 신용 +11.5%" 형태로
    title_parts = []
    for label, _, _, pct in triggers:
        sign = "+" if pct > 0 else ""
        title_parts.append(f"{label} {sign}{pct:.1f}%")
    title = " / ".join(title_parts)

    # 본문
    field_lookup = {label: field for field, _, _, label in RULES}
    body_lines = [
        f"📊 KOSPI 시장 자금 분석 — {last['date']} 기준 전일 대비 알림",
        "",
        "다음 지표에서 임계값(10%)을 넘는 변화가 감지되었습니다:",
        "",
    ]
    for label, prev_v, last_v, pct in triggers:
        sign = "+" if pct > 0 else ""
        field = field_lookup[label]
        body_lines.append(
            f"• {label}: {fmt_value(field, prev_v)} → {fmt_value(field, last_v)}  ({sign}{pct:.2f}%)"
        )
    body_lines += [
        "",
        f"대시보드에서 자세히 보기: {SITE_URL}",
        "",
        "— 자동 발송 (GitHub Actions)",
    ]
    body = "\n".join(body_lines)

    print(f"[알림 {len(triggers)}건] {title}")
    write_output("send", "true")
    write_output("title", title)
    write_output("body", body)
    write_output("date_str", last["date"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
