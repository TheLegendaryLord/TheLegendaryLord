#!/usr/bin/env python3
"""Update only the generated F1 profile block from validated Jolpica results."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.jolpi.ca/ergast/f1"
DRIVER = "max_verstappen"
START = "<!-- F1-TRACKER:START -->"
END = "<!-- F1-TRACKER:END -->"
ROOT = Path(__file__).resolve().parents[1]


def fetch_json(url):
    request = Request(url, headers={
        "User-Agent": "TheLegendaryLord-F1-Profile/1.0 (+https://github.com/TheLegendaryLord/TheLegendaryLord)",
        "Accept": "application/json",
    })
    for attempt in range(3):
        try:
            with urlopen(request, timeout=25) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError("API request exhausted retries")


def points(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid championship points") from error
    if not result.is_finite() or result < 0:
        raise ValueError("Points must be finite and non-negative")
    return result


def number(value):
    result = format(Decimal(str(value)), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def positive_int(value):
    result = int(value)
    if result < 1 or str(result) != str(value):
        raise ValueError("Expected a positive integer")
    return result


def parse_standings(document):
    mr = document["MRData"]
    lists = mr["StandingsTable"]["StandingsLists"]
    if mr.get("series") != "f1" or len(lists) != 1:
        raise ValueError("No unambiguous F1 standings available")
    table = lists[0]
    rows = table["DriverStandings"]
    if int(mr["offset"]) != 0 or int(mr["total"]) != len(rows) or len(rows) < 2:
        raise ValueError("Incomplete standings response")
    drivers = []
    for row in rows:
        driver = row["Driver"]
        wins = int(row["wins"])
        if wins < 0:
            raise ValueError("Invalid win count")
        drivers.append({
            "id": driver["driverId"],
            "name": driver["givenName"] + " " + driver["familyName"],
            "position": positive_int(row["position"]),
            "points": number(points(row["points"])),
            "wins": wins,
            "number": driver.get("permanentNumber", ""),
            "team": " / ".join(c["name"] for c in row["Constructors"]),
        })
    drivers.sort(key=lambda d: d["position"])
    if [d["position"] for d in drivers] != list(range(1, len(drivers) + 1)):
        raise ValueError("Missing or duplicate championship positions")
    if len({d["id"] for d in drivers}) != len(drivers):
        raise ValueError("Duplicate drivers")
    if not any(d["id"] == DRIVER for d in drivers):
        raise ValueError("Max Verstappen is absent from the standings")
    if any(points(a["points"]) < points(b["points"]) for a, b in zip(drivers, drivers[1:])):
        raise ValueError("Championship order contradicts points")
    return {"season": positive_int(table["season"]), "round": positive_int(table["round"]), "drivers": drivers}


def finish_label(result):
    status = result["status"]
    position = positive_int(result["position"])
    if status == "Finished" or re.fullmatch(r"\+\d+ Laps?", status):
        return f"P{position}"
    if status == "Disqualified":
        return "DSQ"
    if status in {"Did not start", "Did not qualify", "Did not prequalify", "Withdrawn"}:
        return "DNS"
    return f"DNF (P{position})"


def parse_race(document, standings):
    mr = document["MRData"]
    races = mr["RaceTable"]["Races"]
    if mr.get("series") != "f1" or len(races) != 1:
        raise ValueError("No unambiguous race result available")
    race = races[0]
    if (int(race["season"]), int(race["round"])) != (standings["season"], standings["round"]):
        raise ValueError("Race and standings refer to different rounds")
    results = race["Results"]
    ids = [r["Driver"]["driverId"] for r in results]
    if int(mr["offset"]) != 0 or int(mr["total"]) != len(results) or not results or len(set(ids)) != len(ids):
        raise ValueError("Incomplete race results")
    datetime.strptime(race["date"], "%Y-%m-%d")
    result = next((r for r in results if r["Driver"]["driverId"] == DRIVER), None)
    return {
        "name": race["raceName"], "date": race["date"],
        "finish": finish_label(result) if result else "DNS / no classified result",
        "points": number(points(result["points"])) if result else "0",
        "status": result["status"] if result else "No result in source",
    }


def md(text):
    return str(text).replace("\\", "\\\\").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ").replace("\r", " ").replace("[", "\\[").replace("]", "\\]").replace("*", "\\*").replace("`", "\\`")


def max_driver(state):
    return next(d for d in state["drivers"] if d["id"] == DRIVER)


def render_svg(state, mobile=False):
    driver = max_driver(state)
    gap = points(state["drivers"][0]["points"]) - points(driver["points"])
    width, height = (560, 500) if mobile else (1100, 270)
    places = [(36, 210, 116), (310, 210, 100), (36, 368, 100)] if mobile else [(40, 156, 88), (400, 156, 88), (755, 156, 88)]
    values = [driver["points"], f'P{driver["position"]}', ("−" if gap else "") + number(gap)]
    labels = ["POINTS", "POSITION", "TO LEADER" if driver["position"] != 1 else "CHAMPIONSHIP LEADER"]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
             '<title id="title">Max Verstappen championship tracker</title>',
             f'<desc id="desc">{escape(driver["points"])} points, position {driver["position"]}, {number(gap)} points behind the leader. Season {state["season"]}, round {state["round"]}.</desc>',
             f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="10" fill="#0c1320" stroke="#2c374b"/>',
             f'<path d="M2 24V{height-24}" stroke="#ed243e" stroke-width="4"/>',
             '<g font-family="Arial,Helvetica,sans-serif">',
             f'<text x="{36 if mobile else 40}" y="44" fill="#f4eedf" font-size="{26 if mobile else 24}" font-weight="700">MAX VERSTAPPEN / #{escape(driver["number"])}</text>']
    if mobile:
        parts.append(f'<text x="36" y="77" fill="#9caabc" font-size="18">{state["season"]} SEASON · ROUND {state["round"]}</text>')
    else:
        parts.append(f'<text x="1060" y="44" text-anchor="end" fill="#9caabc" font-size="18">{state["season"]} SEASON / ROUND {state["round"]}</text>')
    for index, ((x, y, size), value, label) in enumerate(zip(places, values, labels)):
        color = "#ed334a" if index == 1 else "#f4eedf"
        parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="800" letter-spacing="-3">{escape(value)}</text>')
        parts.append(f'<text x="{x+2}" y="{y+38}" fill="#a9b4c4" font-size="{20 if mobile else 17}" letter-spacing="1.2">{label}</text>')
    line_y = height - 52
    parts.extend([f'<path d="M36 {line_y}H{width-36}" stroke="#2c374b"/>',
                  f'<text x="36" y="{height-22}" fill="#a9b4c4" font-size="{18 if mobile else 16}">GRAND PRIX WINS / <tspan fill="#f4eedf" font-weight="700">{driver["wins"]}</tspan></text>',
                  f'<text x="{width-36}" y="{height-22}" text-anchor="end" fill="#9caabc" font-size="{16 if mobile else 14}">MV / F1</text>', '</g></svg>\n'])
    return "\n".join(parts)


def standings_table(state, compact=False):
    drivers = state["drivers"]
    selected = set(range(len(drivers)))
    if compact:
        index = next(i for i, d in enumerate(drivers) if d["id"] == DRIVER)
        selected = set(range(min(5, len(drivers)))) | set(range(max(0, index-1), min(len(drivers), index+2)))
    rows = ["| # | Пилот | Команда | Очки |", "| --: | :-- | :-- | --: |"]
    last = -1
    for i in sorted(selected):
        if i > last + 1:
            rows.append("| … | … | … | … |")
        d = drivers[i]
        cells = [str(d["position"]), md(d["name"]), md(d["team"]), d["points"]]
        if d["id"] == DRIVER:
            cells = [f"**{cell}**" for cell in cells]
        rows.append("| " + " | ".join(cells) + " |")
        last = i
    return "\n".join(rows)


def render_block(state):
    # Include the actual artwork so GitHub's image cache also refreshes after design changes.
    artwork = render_svg(state) + render_svg(state, mobile=True)
    revision = hashlib.sha256(artwork.encode()).hexdigest()[:12]
    driver = max_driver(state)
    gap = number(points(state["drivers"][0]["points"]) - points(driver["points"]))
    alt = f'Max Verstappen: {driver["points"]} очков, P{driver["position"]}, {gap} очков до лидера'
    race = state["race"]
    return f'''{START}

## Max / Championship tracker

<picture>
  <source media="(max-width: 600px)" srcset="./assets/f1-max-mobile.svg?v={revision}" />
  <img src="./assets/f1-max.svg?v={revision}" width="100%" alt="{escape(alt, quote=True)}" />
</picture>

**Последний Гран-при:** {md(race["name"])} · {race["date"]} · **{md(race["finish"])}** · **+{race["points"]} очков в гонке**.

### Зачёт пилотов · {state["season"]}

{standings_table(state, compact=True)}

<details>
<summary>Все пилоты ({len(state["drivers"])})</summary>

{standings_table(state)}

</details>

<sub>Данные после раунда {state["round"]}. Последнее изменение: {state["updated_at"]}. Автопроверка каждые 30 минут. Зачёт обновляется после публикации результатов; возможна задержка.</sub>

<sub>Источник: [Jolpica F1](https://api.jolpi.ca/ergast/f1/{state["season"]}/driverstandings.json) · [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) · [Официальный зачёт F1](https://www.formula1.com/en/results/{state["season"]}/drivers) · [Статус обновления](https://github.com/TheLegendaryLord/TheLegendaryLord/actions/workflows/f1-tracker.yml)</sub>

{END}'''


def replace_block(readme, block):
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("README must contain exactly one tracker marker pair")
    start, end = readme.index(START), readme.index(END)
    if end < start:
        raise ValueError("Tracker markers are reversed")
    return readme[:start] + block + readme[end + len(END):]


def update(root=ROOT, fetch=fetch_json, now=None):
    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    replace_block(readme, START + "\n" + END)
    state = parse_standings(fetch(f"{API}/current/driverstandings.json?limit=100"))
    state["race"] = parse_race(fetch(f'{API}/{state["season"]}/{state["round"]}/results.json?limit=100'), state)
    data_path = root / "data/f1.json"
    old = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else {}
    if old and (state["season"], state["round"]) < (old["season"], old["round"]):
        raise ValueError("Refusing to overwrite newer standings with an older round")
    old_content = {k: v for k, v in old.items() if k != "updated_at"}
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    state["updated_at"] = old["updated_at"] if old_content == state else timestamp
    # Build every output before touching files, so invalid data preserves the last good snapshot.
    outputs = {
        "README.md": replace_block(readme, render_block(state)),
        "data/f1.json": json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        "assets/f1-max.svg": render_svg(state),
        "assets/f1-max-mobile.svg": render_svg(state, mobile=True),
    }
    changed = []
    for relative, content in outputs.items():
        path = root / relative
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
        changed.append(relative)
    return changed


if __name__ == "__main__":
    try:
        changed = update()
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"F1 update failed; last published data retained: {error}", file=sys.stderr)
        sys.exit(1)
    print("Updated: " + ", ".join(changed) if changed else "No new results; profile unchanged.")
