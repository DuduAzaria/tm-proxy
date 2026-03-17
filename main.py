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

def extract_id_from_url(url: str) -> str | None:
    """Extract numeric TM player ID from any TM URL"""
    m = re.search(r'/spieler/(\d+)', url)
    return m.group(1) if m else None

@app.get("/")
def root():
    return {"status": "TM Proxy running ✅", "version": "3.0"}

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
            return {"player_id": player_id, "injuries": [], "note": "No injury history"}

        injuries = []
        tbody = table.find("tbody")
        for row in (tbody.find_all("tr") if tbody else []):
            cols = row.find_all("td")
            if len(cols) < 5:
                continue
            inj = {
                "season":       cols[0].get_text(strip=True),
                "injury":       cols[1].get_text(strip=True),
                "from":         cols[2].get_text(strip=True),
                "until":        cols[3].get_text(strip=True),
                "days":         cols[4].get_text(strip=True),
                "games_missed": cols[5].get_text(strip=True) if len(cols) > 5 else "-",
            }
            if inj["injury"] or inj["from"]:
                injuries.append(inj)

        return {"player_id": player_id, "injuries": injuries}

    except Exception as e:
        return {"error": str(e), "injuries": [], "player_id": player_id}


@app.get("/injuries_by_url")
async def get_injuries_by_url(url: str):
    """Fetch injuries using a full TM verletzungen URL"""
    player_id = extract_id_from_url(url)
    if not player_id:
        return {"error": "No player ID found in URL", "injuries": []}
    return await get_injuries(player_id)


@app.get("/search/{player_name}")
async def search_player(player_name: str):
    """
    Search TM for a player. 
    Strategy: try the TM search page, parse player links.
    Falls back to searching the /spielersuche JSON API which TM uses internally.
    """
    results = []

    # ── Strategy 1: TM internal JSON API (used by their own autocomplete) ──
    try:
        api_url = f"https://www.transfermarkt.com/spieler/suche?term={player_name.replace(' ', '%20')}"
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(api_url, headers={**HEADERS, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
        if r.status_code == 200:
            data = r.json()
            for item in (data if isinstance(data, list) else data.get("suggestions", []))[:5]:
                pid = str(item.get("id") or item.get("playerId") or "")
                name = item.get("value") or item.get("name") or ""
                if pid and name:
                    results.append({"name": name, "id": pid, "club": item.get("club",""), "source": "api"})
    except Exception:
        pass

    # ── Strategy 2: TM schnellsuche HTML page ──
    if not results:
        try:
            url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={player_name.replace(' ', '+')}&Spieler_page=0"
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=HEADERS)

            soup = BeautifulSoup(resp.text, "html.parser")

            # TM search page has h2 headers above each section table
            # Find the "Players" section specifically
            player_section = None
            for h2 in soup.find_all("h2"):
                if "player" in h2.get_text(strip=True).lower() or "spieler" in h2.get_text(strip=True).lower():
                    player_section = h2.find_next("table")
                    break
            
            # Fall back to any table with hauptlink
            tables = [player_section] if player_section else soup.find_all("table", {"class": "items"})
            
            for table in tables:
                if not table:
                    continue
                for td in table.select("td.hauptlink"):
                    a = td.find("a", href=re.compile(r"/spieler/\d+"))
                    if not a:
                        continue
                    pid = extract_id_from_url(a.get("href",""))
                    name = a.get_text(strip=True)
                    if pid and name and not any(r["id"]==pid for r in results):
                        # Get club
                        tr = td.find_parent("tr")
                        club = ""
                        if tr:
                            club_a = tr.find("a", href=re.compile(r"/verein/"))
                            if club_a:
                                club = club_a.get_text(strip=True)
                        results.append({"name": name, "id": pid, "club": club, "source": "html"})
                    if len(results) >= 5:
                        break
                if results:
                    break

        except Exception as e:
            if not results:
                return {"error": str(e), "results": [], "query": player_name}

    # ── Strategy 3: Google-style search via TM search page with different URL ──
    if not results:
        try:
            url2 = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={player_name.replace(' ', '+')}"
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp2 = await client.get(url2, headers=HEADERS)
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            for a in soup2.find_all("a", href=re.compile(r"/spieler/\d+")):
                pid = extract_id_from_url(a.get("href",""))
                name = a.get_text(strip=True)
                if pid and name and len(name) > 3 and not any(r["id"]==pid for r in results):
                    results.append({"name": name, "id": pid, "club": "", "source": "fallback"})
                if len(results) >= 5:
                    break
        except Exception:
            pass

    return {"query": player_name, "results": results, "count": len(results)}
