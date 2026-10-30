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
        "User-Agent": "TheLegendaryLord-F1-Profile/1.1 (+https://github.com/TheLegendaryLord/TheLegendaryLord)",
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
            "surname": driver["familyName"],
            "code": driver.get("code", driver["familyName"][:3].upper()),
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
        "circuit": race.get("Circuit", {}).get("circuitName", ""),
        "venue": race.get("Circuit", {}).get("Location", {}).get("locality", ""),
        "grid": optional_count(result.get("grid")) if result else None,
        "laps": optional_count(result.get("laps")) if result else None,
        "finish": finish_label(result) if result else "NO RESULT",
        "points": number(points(result["points"])) if result else "0",
        "status": result["status"] if result else "No result in source",
    }


def optional_count(value):
    if value is None:
        return None
    result = int(value)
    if result < 0 or str(result) != str(value):
        raise ValueError("Invalid grid or lap count")
    return result


def parse_season_results(document, standings):
    mr = document["MRData"]
    races = mr["RaceTable"]["Races"]
    if mr.get("series") != "f1" or int(mr["offset"]) != 0 or int(mr["total"]) != len(races):
        raise ValueError("Incomplete season race results")
    history = []
    for race in races:
        if int(race["season"]) != standings["season"]:
            raise ValueError("Race history belongs to a different season")
        round_number = positive_int(race["round"])
        if round_number > standings["round"]:
            continue  # The standings may lag behind a freshly published race result.
        results = race["Results"]
        if len(results) != 1 or results[0]["Driver"]["driverId"] != DRIVER:
            raise ValueError("Season result is not unambiguously Max's")
        result = results[0]
        history.append({
            "round": round_number, "name": race["raceName"], "date": race["date"],
            "venue": race.get("Circuit", {}).get("Location", {}).get("locality", race["raceName"]),
            "position": positive_int(result["position"]), "finish": finish_label(result),
            "points": number(points(result["points"])),
        })
    history.sort(key=lambda row: row["round"])
    if len({row["round"] for row in history}) != len(history):
        raise ValueError("Duplicate rounds in season results")
    last = next((row for row in history if row["round"] == standings["round"]), None)
    if standings["race"]["finish"] != "NO RESULT":
        if not last or any(last[key] != standings["race"][key] for key in ("finish", "points")):
            raise ValueError("Season history and last GP disagree")
    classified = [row for row in history if row["finish"] not in {"DSQ", "DNS"}]
    wins = sum(row["position"] == 1 for row in classified)
    if wins != max_driver(standings)["wins"]:
        raise ValueError("Season history and championship win count disagree")
    stats = {
        "starts": sum(row["finish"] != "DNS" for row in history),
        "podiums": sum(row["position"] <= 3 for row in classified),
        "gp_points": number(sum((points(row["points"]) for row in history), Decimal(0))),
    }
    return stats, history[-5:]


def md(text):
    return str(text).replace("\\", "\\\\").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ").replace("\r", " ").replace("[", "\\[").replace("]", "\\]").replace("*", "\\*").replace("`", "\\`")


def max_driver(state):
    return next(d for d in state["drivers"] if d["id"] == DRIVER)


def championship_rows(state):
    drivers = state["drivers"]
    index = next(i for i, driver in enumerate(drivers) if driver["id"] == DRIVER)
    selected = {0, index}
    selected.update(i for i in (index - 1, index + 1) if 0 <= i < len(drivers))
    return [drivers[i] for i in sorted(selected)]


def short(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def render_svg(state, mobile=False):
    driver = max_driver(state)
    race = state["race"]
    stats = state["season_stats"]
    width, height = (640, 1080) if mobile else (1200, 620)
    white, muted, red = "#F0F1F3", "#9AA3B0", "#E82137"
    font = "Arial,Helvetica,sans-serif"
    gap = number(points(state["drivers"][0]["points"]) - points(driver["points"]))
    desc = (f'Max Verstappen: {driver["points"]} points, P{driver["position"]}, '
            f'{gap} points behind the championship leader. {driver["wins"]} GP wins, '
            f'{stats["podiums"]} podiums, {stats["starts"]} GP starts. '
            f'Last Grand Prix: {race["name"]}, {race["finish"]}, {race["points"]} race points.')
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Max Verstappen — season classification and race report</title>',
        f'<desc id="desc">{escape(desc)}</desc>',
        f'<rect width="{width}" height="{height}" fill="#101319"/>',
        f'<path d="M0 2H{width-30}L{width} 32" fill="none" stroke="{red}" stroke-width="4"/>',
        f'<g font-family="{font}">',
    ]

    def text(x, y, value, size=20, color=white, weight=400, anchor="start", spacing=None):
        extra = f' letter-spacing="{spacing}"' if spacing is not None else ""
        parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}"{extra}>{escape(str(value))}</text>')

    def rect(x, y, w, h, color):
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>')

    def line(x1, y1, x2, y2, color="#353B45"):
        parts.append(f'<path d="M{x1} {y1}H{x2}" stroke="{color}"/>' if y1 == y2 else f'<path d="M{x1} {y1}V{y2}" stroke="{color}"/>')

    pad = 32
    text(pad, 34, "DRIVER REPORT", 20 if mobile else 16, muted, 700, spacing=1.6)
    text(width-pad, 34, f'{state["season"]} / ROUND {state["round"]}', 20 if mobile else 16, muted, 700, "end")
    rect(32, 60, 82, 84, white)
    text(73, 124, driver["number"], 66, "#101319", 800, "middle")
    rect(126, 60, 5, 84, "#3671C6")
    text(151, 101, "MAX VERSTAPPEN", 35 if mobile else 40, white, 700, spacing=-0.8)
    team = {"Red Bull": "RED BULL RACING"}.get(driver["team"], driver["team"].upper())
    text(152, 135, short(team, 26), 22 if mobile else 18, muted, 600)
    if not mobile:
        rect(1036, 77, 30, 6, "#AE1C28")
        rect(1036, 83, 30, 6, "#F0F1F3")
        rect(1036, 89, 30, 6, "#21468B")
        text(1080, 95, "NED", 18, muted, 600)
        text(1168, 135, driver["code"], 40, white, 700, "end")
    line(32, 166, width-32, 166)

    if mobile:
        point_x, rank_x, value_y, label_y = 38, 372, 267, 300
        stat_y, stat_label_y = 358, 390
        stat_xs = [38, 246, 454]
        context_y, header_y, row_y, row_h = 443, 476, 515, 40
        pos_x, code_x, name_x, pts_x, delta_x = 38, 113, 194, 493, 606
        table_font = 24
    else:
        point_x, rank_x, value_y, label_y = 32, 302, 272, 303
        stat_y, stat_label_y = 351, 376
        stat_xs = [32, 208, 384]
        context_y, header_y, row_y, row_h = 197, 225, 255, 33
        pos_x, code_x, name_x, pts_x, delta_x = 576, 634, 706, 1004, 1166
        table_font = 21
        line(546, 188, 546, 382)

    text(point_x, value_y, driver["points"], 100 if mobile else 88, white, 800, spacing=-3)
    text(point_x+2, label_y, "CHAMPIONSHIP POINTS", 22 if mobile else 16, muted, 600)
    text(rank_x, value_y, f'P{driver["position"]}', 100 if mobile else 88, white, 800, spacing=-3)
    text(rank_x+2, label_y, "WDC POSITION", 22 if mobile else 16, muted, 600)
    for x, value, label in zip(stat_xs, [driver["wins"], stats["podiums"], stats["starts"]], ["GP WINS", "PODIUMS", "GP STARTS"]):
        text(x, stat_y, value, 38 if mobile else 30, white, 700)
        text(x, stat_label_y, label, 21 if mobile else 15, muted, 600)

    if mobile:
        line(32, 418, width-32, 418)
    text(pos_x, context_y, "CHAMPIONSHIP CONTEXT", 22 if mobile else 15, muted, 700, spacing=1.1)
    text(pos_x, header_y, "POS", 18 if mobile else 13, muted, 600)
    text(code_x, header_y, "DRIVER", 18 if mobile else 13, muted, 600)
    text(pts_x, header_y, "PTS", 18 if mobile else 13, muted, 600, "end")
    text(delta_x, header_y, "Δ TO VER", 18 if mobile else 13, muted, 600, "end")
    for index, other in enumerate(championship_rows(state)):
        y = row_y + index * row_h
        is_max = other["id"] == DRIVER
        color = "#101319" if is_max else white
        if is_max:
            rect(pos_x-8, y-(29 if mobile else 24), width-pos_x-24, 36 if mobile else 30, white)
            rect(pos_x-8, y-(29 if mobile else 24), 4, 36 if mobile else 30, red)
        delta = points(other["points"]) - points(driver["points"])
        delta_text = "—" if is_max else ("+" if delta > 0 else "−" if delta < 0 else "") + number(abs(delta))
        text(pos_x, y, f'P{other["position"]}', table_font, color, 700 if is_max else 400)
        text(code_x, y, other["code"], table_font, color, 700)
        text(name_x, y, short(other["surname"].upper(), 12 if mobile else 17), table_font-3, color, 700 if is_max else 400)
        text(pts_x, y, other["points"], table_font, color, 700 if is_max else 400, "end")
        text(delta_x, y, delta_text, table_font, color if is_max else "#D5B76B" if delta > 0 else muted, 600, "end")

    band_y = 660 if mobile else 403
    rect(32, band_y, width-64, 32, "#252B34")
    text(44, band_y+23, "LAST GRAND PRIX", 21 if mobile else 15, white, 700, spacing=0.6)
    day = datetime.strptime(race["date"], "%Y-%m-%d")
    month = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()[day.month-1]
    text(width-44, band_y+23, f"{day.day:02} {month} {day.year}", 20 if mobile else 15, muted, 600, "end")
    event = race["name"].replace("Grand Prix", "GP").upper()
    text(32, band_y+66, short(event, 31 if mobile else 33), 29 if mobile else 25, white, 700, spacing=-0.4)
    venue = " / ".join(value for value in [race["venue"].upper(), race["circuit"].upper()] if value)
    text(32, band_y+94, short(venue, 48 if mobile else 52), 20 if mobile else 14, muted)
    metric_y = band_y+160 if mobile else band_y+66
    metric_xs = [38, 192, 346, 500] if mobile else [694, 838, 982, 1126]
    grid = "—" if not race["grid"] else f'P{race["grid"]}'
    finish = race["finish"]
    if finish.startswith("DNF"):
        finish = "DNF"
    elif finish == "NO RESULT":
        finish = "N/A"
    values = [grid, finish, "+"+race["points"], "—" if race["laps"] is None else race["laps"]]
    for x, value, label in zip(metric_xs, values, ["GRID", "FINISH", "RACE PTS", "LAPS"]):
        text(x, metric_y, value, 42 if mobile else 36, white, 700)
        text(x, metric_y+29, label, 20 if mobile else 14, muted, 600)

    form_y = 895 if mobile else 535
    text(32, form_y, "LAST 5 GRANDS PRIX", 22 if mobile else 15, muted, 700, spacing=1)
    form = state["recent_results"]
    cell_width = 115 if mobile else 190
    start_x = 32 if mobile else 220
    for index, result in enumerate(form):
        x = start_x + index*cell_width
        if index:
            line(x-12, form_y+12 if mobile else form_y-8, x-12, form_y+134 if mobile else form_y+50)
        if mobile:
            text(x, form_y+40, f'R{result["round"]}', 24, muted, 600)
            text(x, form_y+92, result["finish"].split(" ")[0], 40, white, 700)
            text(x, form_y+128, "+"+result["points"], 26, "#D5B76B", 600)
        else:
            text(x, form_y+5, f'R{result["round"]} / '+short(result["venue"].upper(), 16), 14, muted, 600)
            text(x, form_y+45, result["finish"].split(" ")[0], 30, white, 700)
            text(x+151, form_y+43, "+"+result["points"], 20, "#D5B76B", 600, "end")
    text(32, height-20, "RECENT FORM / GRAND PRIX RESULTS ONLY", 18 if mobile else 12, muted, spacing=0.7)
    parts.extend(["</g>", "</svg>\n"])
    return "\n".join(parts)


def standings_table(state, compact=False):
    drivers = state["drivers"]
    selected = set(range(len(drivers)))
    if compact:
        index = next(i for i, d in enumerate(drivers) if d["id"] == DRIVER)
        selected = set(range(min(5, len(drivers)))) | set(range(max(0, index-1), min(len(drivers), index+2)))
    rows = ["| # | Driver | Team | Points |", "| --: | :-- | :-- | --: |"]
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
    alt = f'Max Verstappen: {driver["points"]} points, P{driver["position"]}, {gap} points behind the leader'
    race = state["race"]
    return f'''{START}

## Max Verstappen / Season report

<picture>
  <source media="(max-width: 600px)" srcset="./assets/f1-max-mobile.svg?v={revision}" />
  <img src="./assets/f1-max.svg?v={revision}" width="100%" alt="{escape(alt, quote=True)}" />
</picture>

**Last Grand Prix:** {md(race["name"])} · {race["date"]} · **{md(race["finish"])}** · **+{race["points"]} race points**.

### Drivers' standings · {state["season"]}

{standings_table(state, compact=True)}

<details>
<summary>All drivers ({len(state["drivers"])})</summary>

{standings_table(state)}

</details>

<sub>Standings after Round {state["round"]}. Last data change: {state["updated_at"]}. Checked every 30 minutes. Standings update after results are published; updates may be delayed.</sub>

<sub>Source: [Jolpica F1](https://api.jolpi.ca/ergast/f1/{state["season"]}/driverstandings.json) · [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) · [Official F1 standings](https://www.formula1.com/en/results/{state["season"]}/drivers) · [Update status](https://github.com/TheLegendaryLord/TheLegendaryLord/actions/workflows/f1-tracker.yml)</sub>

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
    state["season_stats"], state["recent_results"] = parse_season_results(
        fetch(f'{API}/{state["season"]}/drivers/{DRIVER}/results.json?limit=100'), state)
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


