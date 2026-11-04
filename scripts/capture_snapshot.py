import subprocess
import time
import json
import base64
from pathlib import Path
import requests
import websocket

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
OUTPUT_DIR = Path("assets")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "dashboard_snapshot.png"

def capture():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        "--window-size=1600,1200",
        "--disable-gpu",
        "http://localhost:8501"
    ]
    proc = subprocess.Popen(cmd)
    try:
        # Give Streamlit 18 seconds to complete initial API fetches, calculate valuation, and render Plotly charts
        print("Waiting 18 seconds for Streamlit dashboard to render...")
        time.sleep(18)

        # Get WebSocket debugger URL
        tabs = requests.get("http://127.0.0.1:9222/json", timeout=5).json()
        page_tab = next((t for t in tabs if t.get("type") == "page"), tabs[0])
        ws_url = page_tab["webSocketDebuggerUrl"]

        ws = websocket.create_connection(ws_url, timeout=15)

        # Request screenshot
        req = {
            "id": 1,
            "method": "Page.captureScreenshot",
            "params": {
                "format": "png",
                "quality": 100
            }
        }
        ws.send(json.dumps(req))

        while True:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == 1:
                img_bytes = base64.b64decode(msg["result"]["data"])
                with open(OUTPUT_PATH, "wb") as f:
                    f.write(img_bytes)
                print(f"[OK] Screenshot saved: {OUTPUT_PATH} ({len(img_bytes)} bytes)")
                break

        ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

if __name__ == "__main__":
    capture()
