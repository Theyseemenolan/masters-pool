import csv
import os
import requests
import unicodedata
from collections import defaultdict
from datetime import datetime

# =========================
# SETTINGS
# =========================
DATA_DIR = "/Users/nolanmckenna/Documents/Masters Pool 2026"
PICKS_FILE = os.path.join(DATA_DIR, "picks.csv")
OUTPUT_HTML = os.path.join(DATA_DIR, "index.html")

API_KEY = "0558d93c16msh58f9026da6cef3ep12ee9cjsn6906fd4703c9"
API_HOST = "live-golf-data.p.rapidapi.com"
API_URL = f"https://{API_HOST}/leaderboard"

ORG_ID = "1"
TOURN_ID = "014"   # Masters
YEAR = "2024"      # Change to 2026 when needed


# =========================
# NAME HELPERS
# =========================
def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def normalize_name(name: str) -> str:
    name = strip_accents(name)
    name = name.lower()
    for ch in [".", "'", "’", "-", ","]:
        name = name.replace(ch, " ")
    name = " ".join(name.split())
    return name


ALIASES = {
    normalize_name("JT Poston"): normalize_name("J. T. Poston"),
    normalize_name("Ludvig Aberg"): normalize_name("Ludvig Åberg"),
    normalize_name("Joaquin Niemann"): normalize_name("Joaquín Niemann"),
    normalize_name("Jose Maria Olazabal"): normalize_name("José María Olazábal"),
    normalize_name("Thorbjorn Olesen"): normalize_name("Thorbjørn Olesen"),
    normalize_name("Nicolai Hojgaard"): normalize_name("Nicolai Højgaard"),
}


def alias_name(name: str) -> str:
    n = normalize_name(name)
    return ALIASES.get(n, n)


# =========================
# LOAD PICKS
# =========================
def clean_header(name):
    return name.strip().lower() if name else ""


def load_picks(filename):
    picks = []

    with open(filename, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        raw_headers = reader.fieldnames or []
        cleaned = {clean_header(name): name for name in raw_headers}

        entry_col = cleaned.get("entry")
        player_col = cleaned.get("player")

        if (not entry_col or not player_col) and len(raw_headers) >= 2:
            entry_col = raw_headers[0]
            player_col = raw_headers[1]

        if not entry_col or not player_col:
            raise ValueError(
                f"picks.csv must have at least two columns for entry and player. Found headers: {raw_headers}"
            )

        for row in reader:
            entry = row[entry_col].strip()
            player = row[player_col].strip()

            if not entry or not player:
                continue

            picks.append((entry, player))

    return picks


# =========================
# FETCH API LEADERBOARD
# =========================
def fetch_leaderboard():
    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
    }

    params = {
        "orgId": ORG_ID,
        "tournId": TOURN_ID,
        "year": YEAR,
    }

    response = requests.get(API_URL, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_score(score_text):
    if score_text is None:
        return None

    score_text = str(score_text).strip()

    if score_text == "":
        return None
    if score_text.upper() == "E":
        return 0

    return int(score_text)


def build_score_lookup(api_data):
    rows = api_data.get("leaderboardRows", [])
    scores_by_normalized_name = {}
    raw_name_map = {}
    position_map = {}
    status_map = {}

    for row in rows:
        first = str(row.get("firstName", "")).strip()
        last = str(row.get("lastName", "")).strip()
        total = row.get("total")
        position = str(row.get("position", "")).strip()
        status = str(row.get("status", "")).strip()

        if not first or not last:
            continue

        full_name = f"{first} {last}"
        score = parse_score(total)

        if score is None:
            continue

        norm = alias_name(full_name)
        scores_by_normalized_name[norm] = score
        raw_name_map[norm] = full_name
        position_map[norm] = position
        status_map[norm] = status

    return scores_by_normalized_name, raw_name_map, position_map, status_map


# =========================
# CALCULATE STANDINGS
# =========================
def calculate_standings(picks, scores_lookup):
    totals = defaultdict(int)
    missing_players = defaultdict(list)
    team_players = defaultdict(list)

    for entry, player in picks:
        normalized_pick = alias_name(player)

        player_score = None
        if normalized_pick in scores_lookup:
            player_score = scores_lookup[normalized_pick]
            totals[entry] += player_score
        else:
            missing_players[entry].append(player)

        team_players[entry].append((player, normalized_pick, player_score))

    standings = sorted(totals.items(), key=lambda x: x[1])
    return standings, missing_players, team_players


# =========================
# HTML HELPERS
# =========================
def score_display(score):
    if score is None:
        return "—"
    if score == 0:
        return "E"
    if score > 0:
        return f"+{score}"
    return str(score)


def escape_html(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html(api_data, standings, team_players, scores_lookup, raw_name_map, position_map, status_map):
    updated = datetime.now().strftime("%Y-%m-%d %I:%M %p")

    standings_rows = []
    for rank, (entry, total) in enumerate(standings, start=1):
        standings_rows.append(
            f"""
            <tr>
              <td>{rank}</td>
              <td>{escape_html(entry)}</td>
              <td>{escape_html(score_display(total))}</td>
            </tr>
            """
        )

    teams_html = []
    for entry, _total in standings:
        players_html = []

        for original_name, normalized_name, player_score in team_players[entry]:
            api_name = raw_name_map.get(normalized_name, original_name)
            position = position_map.get(normalized_name, "")
            status = status_map.get(normalized_name, "")

            badge = ""
            if status == "cut":
                badge = '<span class="badge cut">CUT</span>'
            elif status == "complete":
                badge = '<span class="badge complete">F</span>'

            pos_text = f" ({position})" if position and position != "-" else ""

            players_html.append(
                f"""
                <tr>
                  <td>{escape_html(api_name)}</td>
                  <td>{escape_html(score_display(player_score))}</td>
                  <td>{escape_html(pos_text)}</td>
                  <td>{badge}</td>
                </tr>
                """
            )

        teams_html.append(
            f"""
            <section class="card">
              <h2>{escape_html(entry)}</h2>
              <table>
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Score</th>
                    <th>Pos</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(players_html)}
                </tbody>
              </table>
            </section>
            """
        )

    tournament_status = api_data.get("status", "")
    round_status = api_data.get("roundStatus", "")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="60">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Masters Pool</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 24px;
      background: #f5f5f5;
      color: #222;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    h1 {{
      margin-bottom: 6px;
    }}
    .sub {{
      color: #666;
      margin-bottom: 24px;
    }}
    .card {{
      background: white;
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid #e5e5e5;
    }}
    th {{
      background: #fafafa;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: bold;
    }}
    .cut {{
      background: #ffe2e2;
      color: #a10000;
    }}
    .complete {{
      background: #e4f6e4;
      color: #116611;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 20px;
    }}
    @media (min-width: 900px) {{
      .grid {{
        grid-template-columns: 1fr 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Masters Pool</h1>
    <div class="sub">
      Last updated: {escape_html(updated)}<br>
      Tournament status: {escape_html(tournament_status)} | Round status: {escape_html(round_status)}
    </div>

    <section class="card">
      <h2>Standings</h2>
      <table>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Entry</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {''.join(standings_rows)}
        </tbody>
      </table>
    </section>

    <div class="grid">
      {''.join(teams_html)}
    </div>
  </div>
</body>
</html>
"""
    return html


# =========================
# MAIN
# =========================
def main():
    print("Using picks file:", PICKS_FILE)
    print("Calling API:", API_URL)
    print("Writing HTML to:", OUTPUT_HTML)

    picks = load_picks(PICKS_FILE)
    api_data = fetch_leaderboard()

    scores_lookup, raw_name_map, position_map, status_map = build_score_lookup(api_data)
    standings, missing_players, team_players = calculate_standings(picks, scores_lookup)

    html = build_html(
        api_data,
        standings,
        team_players,
        scores_lookup,
        raw_name_map,
        position_map,
        status_map,
    )

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print("\nSTANDINGS")
    print("-" * 35)
    for i, (entry, total) in enumerate(standings, start=1):
        print(f"{i:>2}. {entry:<18} {score_display(total)}")

    print(f"\nWebsite updated: {OUTPUT_HTML}")

    print("\nPLAYERS NOT FOUND IN API LEADERBOARD")
    print("-" * 35)
    any_missing = False
    for entry, players in missing_players.items():
        if players:
            any_missing = True
            print(f"{entry}:")
            for player in players:
                print(f"   - {player}")

    if not any_missing:
        print("None")


if __name__ == "__main__":
    main()
