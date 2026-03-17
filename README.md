# TM Proxy — Transfermarkt Injury Fetcher

## Deploy on Render.com (free, 5 minutes)

1. Upload this folder to GitHub (new repo)
2. Go to render.com → New → Web Service
3. Connect your GitHub repo
4. Settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Plan: Free
5. Click Deploy → wait ~2 minutes
6. Copy your URL: `https://tm-proxy-xxxx.onrender.com`

## Endpoints

GET /injuries/{player_id}
  → Returns full injury history as JSON
  → player_id = numeric ID from TM URL
  
GET /search/{player_name}
  → Returns player ID from name search

## Examples
https://your-render-url.onrender.com/injuries/684998   ← Kings Kangwa
https://your-render-url.onrender.com/search/Kangwa
