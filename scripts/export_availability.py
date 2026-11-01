"""노션 「예약」 DB → data/availability.json (예약된 시간대만, 개인정보 없음).

사이트 캘린더가 이 파일을 읽어 '예약 마감' 시간을 보여준다.
노션 예약 DB가 모든 채널(네이버·스페이스클라우드·DM 등) 예약의 기준이다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib

import requests

DS_ID = "0e808da0-b9bb-4baa-a24f-22a1c1b9353e"
KST = dt.timezone(dt.timedelta(hours=9))
DAYS_AHEAD = 62
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "availability.json"


def query_all(token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": "2025-09-03",
               "Content-Type": "application/json"}
    rows, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(f"https://api.notion.com/v1/data_sources/{DS_ID}/query",
                          headers=headers, json=body, timeout=30)
        r.raise_for_status()
        j = r.json()
        rows += j["results"]
        if not j.get("has_more"):
            return rows
        cursor = j["next_cursor"]


def parse(iso: str | None) -> dt.datetime | None:
    if not iso or "T" not in iso:
        return None
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (t if t.tzinfo else t.replace(tzinfo=KST)).astimezone(KST)


def main() -> None:
    now = dt.datetime.now(KST)
    horizon = now + dt.timedelta(days=DAYS_AHEAD)
    busy = []
    for p in query_all(os.environ["NOTION_API_KEY"]):
        props = p["properties"]
        status = (props.get("상태", {}).get("select") or {}).get("name")
        if status == "❌ 취소":
            continue
        d = props.get("이용 시간", {}).get("date") or {}
        start, end = parse(d.get("start")), parse(d.get("end"))
        product = (props.get("상품", {}).get("select") or {}).get("name")
        if start and not end and product == "올데이 패키지":
            end = start + dt.timedelta(hours=8)
        if not start or not end or end < now or start > horizon:
            continue
        busy.append({"start": start.strftime("%Y-%m-%dT%H:%M"), "end": end.strftime("%Y-%m-%dT%H:%M")})
    busy.sort(key=lambda b: b["start"])
    out = {"updated": now.strftime("%Y-%m-%d %H:%M"), "open": "10:00", "close": "24:00", "busy": busy}
    OUT.parent.mkdir(exist_ok=True)
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    new = json.dumps(out, ensure_ascii=False, indent=1)
    # 예약 변화가 없으면 파일을 그대로 둬서 불필요한 커밋을 만들지 않는다
    if old and json.loads(old)["busy"] == busy:
        print("변화 없음")
        return
    OUT.write_text(new + "\n", encoding="utf-8")
    print(f"예약 {len(busy)}건 반영")


if __name__ == "__main__":
    main()
