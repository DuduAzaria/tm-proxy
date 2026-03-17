from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

@app.get("/")
def root():
    return {"status": "TM Proxy running ✅"}

@app.get("/injuries/{player_id}")
async def get_injuries(player_id: str):
    """
    Fetch injury history for a player from Transfermarkt.
    player_id = the numeric ID from the TM URL (e.g. 684998 for Kings Kangwa)
    """
    url = f"https://www.transfermarkt.com/a/verletzungen/spieler/{player_id}/plus/1"
    
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
        
        if resp.status_code != 200:
            return {"error": f"TM returned {resp.status_code}", "injuries": []}
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Parse the injury table
        table = soup.find("table", {"class": "items"})
        if not table:
            return {"player_id": player_id, "injuries": [], "note": "No injury table found"}
        
        injuries = []
        rows = table.find("tbody").find_all("tr") if table.find("tbody") else []
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue
            injuries.append({
                "season":       cols[0].get_text(strip=True),
                "injury":       cols[1].get_text(strip=True),
                "from":         cols[2].get_text(strip=True),
                "until":        cols[3].get_text(strip=True),
                "days":         cols[4].get_text(strip=True),
                "games_missed": cols[5].get_text(strip=True) if len(cols) > 5 else "-",
            })
        
        return {
            "player_id": player_id,
            "source_url": url,
            "injuries": injuries
        }
    
    except Exception as e:
        return {"error": str(e), "injuries": []}

@app.get("/search/{player_name}")
async def search_player(player_name: str):
    """Search for a player on TM and return their ID"""
    url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={player_name.replace(' ', '+')}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for a in soup.select("table.items td.hauptlink a")[:5]:
            href = a.get("href", "")
            if "/spieler/" in href:
                pid = href.split("/spieler/")[1].split("/")[0]
                results.append({"name": a.get_text(strip=True), "id": pid, "url": f"https://www.transfermarkt.com{href}"})
        return {"results": results}
    except Exception as e:
        return {"error": str(e), "results": []}
