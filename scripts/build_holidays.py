#!/usr/bin/env python3
"""Fetch a bounded Israeli holiday snapshot for the GTFS publication window.

Hebcal is queried only in CI, never from the visitor's browser.
Source: https://www.hebcal.com/home/developer-apis (CC BY 4.0).
"""
import argparse
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# A deliberately bounded mapping: unrelated omer, Torah reading and Shabbat
# notices must not be promoted to names of special public-transport timetables.
KNOWN = {
 "Erev Rosh Hashana": "ערב ראש השנה",
 "Rosh Hashana": "ראש השנה",
 "Rosh Hashanah": "ראש השנה",
 "Tzom Gedaliah": "צום גדליה",
 "Erev Yom Kippur": "ערב יום כיפור",
 "Yom Kippur": "יום כיפור",
 "Erev Sukkot": "ערב סוכות",
 "Sukkot VII": "הושענא רבה",
 "Sukkot": "סוכות",
 "Sukkot Chol ha-Moed": "חול המועד סוכות",
 "Hoshana Raba": "הושענא רבה",
 "Shmini Atzeret": "שמיני עצרת ושמחת תורה",
 "Simchat Torah": "שמיני עצרת ושמחת תורה",
 "Chanukah": "חנוכה",
 "Asara B'Tevet": "עשרה בטבת",
 "Tu BiShvat": "ט״ו בשבט",
 "Ta'anit Esther": "תענית אסתר",
 "Purim": "פורים",
 "Shushan Purim": "שושן פורים",
 "Purim Katan": "פורים קטן",
 "Shushan Purim Katan": "שושן פורים קטן",
 "Erev Pesach": "ערב פסח",
 "Pesach VII": "שביעי של פסח",
 "Pesach": "פסח",
 "Pesach Chol ha-Moed": "חול המועד פסח",
 "Pesach Sheni": "פסח שני",
 "Yom HaShoah": "יום השואה",
 "Yom HaZikaron": "יום הזיכרון",
 "Yom HaAtzma'ut": "יום העצמאות",
 "Yom HaAtzmaut": "יום העצמאות",
 "Lag BaOmer": "ל״ג בעומר",
 "Yom Yerushalayim": "יום ירושלים",
 "Erev Shavuot": "ערב שבועות",
 "Shavuot": "שבועות",
 "Tzom Tammuz": "שבעה עשר בתמוז",
 "Erev Tish'a B'Av": "ערב תשעה באב",
 "Tish'a B'Av": "תשעה באב",
 "Tu B'Av": "ט״ו באב",
 "Yom HaAliyah": "יום העלייה",
 "Yom HaAliyah School Observance": "יום העלייה במערכת החינוך",
 "Yitzhak Rabin Memorial Day": "יום הזיכרון ליצחק רבין",
 "Ben-Gurion Day": "יום בן-גוריון",
 "Swords of Iron War Memorial Day": "יום הזיכרון לחללי מלחמת חרבות ברזל",
 "Sigd": "סיגד",
}
# Event descriptions from Hebcal may include day numbers e.g. Chanukah: 3 Candles.
def label(title):
    title = str(title).strip()
    if title.startswith("Sukkot ") and ("CH" in title or "Chol" in title):
        return "חול המועד סוכות"
    if title.startswith("Pesach ") and ("CH" in title or "Chol" in title):
        return "חול המועד פסח"
    for prefix, name in sorted(KNOWN.items(), key=lambda x: -len(x[0])):
        if title == prefix or title.startswith(prefix + " ") or title.startswith(prefix + ":") or title.startswith(prefix + " I") or title.startswith(prefix + " VII"):
            return name
    return None

def generate(start, days, destination):
    end = start + timedelta(days=days-1)
    query = urllib.parse.urlencode({
        "v":"1","cfg":"json","start":start.isoformat(),"end":end.isoformat(),
        "maj":"on","min":"on","mod":"on","mf":"on","i":"on","nx":"off",
        "ss":"off","s":"off","o":"off","c":"off","lg":"s"
    })
    request = urllib.request.Request("https://www.hebcal.com/hebcal?"+query,
        headers={"User-Agent":"LuzMaker/1.0 (Hebcal attribution; GitHub Pages static holiday labels)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.load(response)
    events = {}
    for event in data.get("items", []):
        iso = event.get("date", "")[:10]
        name = label(event.get("title", ""))
        if iso and name:
            events.setdefault(iso, [])
            if name not in events[iso]:
                events[iso].append(name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"source":"Hebcal.com","license":"CC BY 4.0","start":start.isoformat(),"end":end.isoformat(),"events":events},ensure_ascii=False),encoding="utf-8")
    print("Hebcal holiday snapshot:",len(events),"days",destination)

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--start",default=date.today().isoformat())
    p.add_argument("--days",type=int,default=20)
    args=p.parse_args()
    generate(date.fromisoformat(args.start),args.days,Path(args.output))
