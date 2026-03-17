from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

@app.get("/")
def root():
    return {"status": "TM Proxy running ✅", "version": "2.0"}

@app.get("/injuries/{player_id}")
async def get_injuries(player_id: str):
    """Fetch full injury history for a player by TM ID"""
    url = f"https://www.transfermarkt.com/a/verletzungen/spieler/{player_id}/plus/1"
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)

        if resp.status_code != 200:
            return {"error": f"TM returned {resp.status_code}", "injuries": [], "player_id": player_id}

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", {"class": "items"})
        if not table:
            return {"player_id": player_id, "injuries": [], "note": "No injury table found — player may have no injury history"}

        injuries = []
        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else []

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue
            injury = {
                "season":       cols[0].get_text(strip=True),
                "injury":       cols[1].get_text(strip=True),
                "from":         cols[2].get_text(strip=True),
                "until":        cols[3].get_text(strip=True),
                "days":         cols[4].get_text(strip=True),
                "games_missed": cols[5].get_text(strip=True) if len(cols) > 5 else "-",
            }
            if injury["injury"] or injury["from"]:
                injuries.append(injury)

        return {
            "player_id": player_id,
            "source_url": f"https://www.transfermarkt.com/a/verletzungen/spieler/{player_id}",
            "injuries": injuries
        }

    except Exception as e:
        return {"error": str(e), "injuries": [], "player_id": player_id}


@app.get("/search/{player_name}")
async def search_player(player_name: str):
    """Search for a player on TM — returns list of matches with their IDs"""
    url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={player_name.replace(' ', '+')}&Spieler_page=0"
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        # Strategy 1: hauptlink cells
        for td in soup.select("td.hauptlink"):
            a = td.find("a", href=re.compile(r"/spieler/\d+"))
            if a:
                href = a.get("href", "")
                m = re.search(r"/spieler/(\d+)", href)
                if m:
                    pid = m.group(1)
                    name = a.get_text(strip=True)
                    # Get club from next td if available
                    parent_tr = td.find_parent("tr")
                    club = ""
                    if parent_tr:
                        club_td = parent_tr.find("td", {"class": "zentriert"})
                        club_a = parent_tr.find("a", href=re.compile(r"/verein/"))
                        if club_a:
                            club = club_a.get_text(strip=True)
                    results.append({
                        "name": name,
                        "id": pid,
                        "club": club,
                        "injuries_url": f"https://www.transfermarkt.com/a/verletzungen/spieler/{pid}",
                    })
                    if len(results) >= 5:
                        break

        # Strategy 2: any /spieler/ link as fallback
        if not results:
            for a in soup.find_all("a", href=re.compile(r"/spieler/\d+")):
                href = a.get("href", "")
                m = re.search(r"/spieler/(\d+)", href)
                name = a.get_text(strip=True)
                if m and name and len(name) > 2:
                    pid = m.group(1)
                    if not any(r["id"] == pid for r in results):
                        results.append({"name": name, "id": pid, "club": "", "injuries_url": f"https://www.transfermarkt.com/a/verletzungen/spieler/{pid}"})
                    if len(results) >= 5:
                        break

        return {"query": player_name, "results": results, "count": len(results)}

    except Exception as e:
        return {"error": str(e), "results": [], "query": player_name}
