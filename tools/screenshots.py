#!/usr/bin/env python3
"""
docs/images/atlas-map.jpg and atlas-airlines.jpg: screenshots of the atlas for the README.
Best effort: needs  pip install playwright  and  playwright install chromium  (skipped quietly if missing).
"""
import contextlib, http.server, socketserver, threading
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(country="NZ"):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("screenshots: playwright not installed, skipped"); return
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass
    handler = partial(Quiet, directory=str(ROOT))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}/atlas.html"
        out = ROOT / "docs" / "images"
        out.mkdir(parents=True, exist_ok=True)
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                pg = b.new_page(viewport={"width": 1200, "height": 820})
                pg.goto(base + "#" + country); pg.wait_for_selector("#grid > *"); pg.wait_for_timeout(600)
                pg.evaluate("window.scrollTo(0, 0)")
                pg.screenshot(path=str(out / "atlas-map.jpg"), type="jpeg", quality=85)
                pg.click("#vair"); pg.wait_for_selector(".al"); pg.wait_for_timeout(600)
                pg.evaluate("document.querySelector('#pick').scrollIntoView()")
                pg.screenshot(path=str(out / "atlas-airlines.jpg"), type="jpeg", quality=85)
                b.close()
            print("screenshots: docs/images/atlas-map.jpg, atlas-airlines.jpg")
        except Exception as e:
            print("screenshots: skipped:", str(e)[:160])
        finally:
            srv.shutdown()


if __name__ == "__main__":
    build()
