import os
import json
import threading
from datetime import datetime

import pandas as pd
from flask import Flask, render_template, jsonify, request, send_file

from scraper import PepitesScraper
from scraper_chefs_etablissement import ChefsEtablissementScraper

app = Flask(__name__)

# Global state for scraping progress
scrape_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "message": "",
    "results": [],
}
state_lock = threading.Lock()

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def progress_callback(current, total, message):
    with state_lock:
        scrape_state["progress"] = current
        scrape_state["total"] = total
        scrape_state["message"] = message


def run_scrape(num_pages, with_details, category=None):
    with state_lock:
        scrape_state["running"] = True
        scrape_state["progress"] = 0
        scrape_state["total"] = num_pages
        scrape_state["message"] = "Démarrage..."
        scrape_state["results"] = []

    scraper = PepitesScraper()
    results = scraper.scrape(
        num_pages=num_pages,
        with_details=with_details,
        category=category,
        progress_callback=progress_callback,
    )

    with state_lock:
        scrape_state["results"] = results
        scrape_state["running"] = False
        scrape_state["message"] = f"Terminé ! {len(results)} startups trouvées."


@app.route("/")
def index():
    scraper = PepitesScraper()
    try:
        categories = scraper.fetch_categories()
    except Exception:
        categories = {}
    return render_template("index.html", categories=categories)


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    with state_lock:
        if scrape_state["running"]:
            return jsonify({"error": "Un scraping est déjà en cours."}), 409

    data = request.get_json(force=True)
    raw_pages = int(data.get("num_pages", 1))
    num_pages = 0 if raw_pages == 0 else min(raw_pages, 100)
    with_details = bool(data.get("with_details", False))
    category = data.get("category") or None

    thread = threading.Thread(target=run_scrape, args=(num_pages, with_details, category))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started", "num_pages": num_pages})


@app.route("/api/progress")
def api_progress():
    with state_lock:
        return jsonify(
            {
                "running": scrape_state["running"],
                "progress": scrape_state["progress"],
                "total": scrape_state["total"],
                "message": scrape_state["message"],
                "count": len(scrape_state["results"]),
            }
        )


@app.route("/api/results")
def api_results():
    with state_lock:
        return jsonify(scrape_state["results"])


@app.route("/api/export/<fmt>")
def api_export(fmt):
    with state_lock:
        results = list(scrape_state["results"])

    if not results:
        return jsonify({"error": "Aucune donnée à exporter."}), 400

    df = pd.DataFrame(results)
    # Drop internal column
    df = df.drop(columns=["detail_url"], errors="ignore")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fmt == "csv":
        filepath = os.path.join(DATA_DIR, f"pepites_{timestamp}.csv")
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        return send_file(filepath, as_attachment=True, download_name=f"pepites_{timestamp}.csv")
    elif fmt == "excel":
        filepath = os.path.join(DATA_DIR, f"pepites_{timestamp}.xlsx")
        df.to_excel(filepath, index=False)
        return send_file(filepath, as_attachment=True, download_name=f"pepites_{timestamp}.xlsx")
    else:
        return jsonify({"error": "Format non supporté. Utilisez 'csv' ou 'excel'."}), 400


# ---------------------------------------------------------------------------
# Chefs d'établissement – état global
# ---------------------------------------------------------------------------
chefs_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "message": "",
    "results": [],
}
chefs_lock = threading.Lock()


def chefs_progress_callback(current, total, message):
    with chefs_lock:
        chefs_state["progress"] = current
        chefs_state["total"] = total
        chefs_state["message"] = message


def run_chefs_scrape(departement, max_records):
    with chefs_lock:
        chefs_state["running"] = True
        chefs_state["progress"] = 0
        chefs_state["total"] = 1
        chefs_state["message"] = "Démarrage…"
        chefs_state["results"] = []

    scraper = ChefsEtablissementScraper()
    results = scraper.scrape(
        departement=departement,
        max_records=max_records,
        progress_callback=chefs_progress_callback,
    )

    with chefs_lock:
        chefs_state["results"] = results
        chefs_state["running"] = False
        chefs_state["message"] = f"Terminé ! {len(results)} établissements récupérés."


@app.route("/chefs-etablissement")
def chefs_etablissement():
    return render_template("chefs_etablissement.html")


@app.route("/api/chefs/scrape", methods=["POST"])
def api_chefs_scrape():
    with chefs_lock:
        if chefs_state["running"]:
            return jsonify({"error": "Un scraping est déjà en cours."}), 409

    data = request.get_json(force=True)
    departement = (data.get("departement") or "").strip() or None
    max_records = int(data.get("max_records", 0))

    thread = threading.Thread(
        target=run_chefs_scrape, args=(departement, max_records)
    )
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started"})


@app.route("/api/chefs/progress")
def api_chefs_progress():
    with chefs_lock:
        return jsonify({
            "running": chefs_state["running"],
            "progress": chefs_state["progress"],
            "total": chefs_state["total"],
            "message": chefs_state["message"],
            "count": len(chefs_state["results"]),
        })


@app.route("/api/chefs/results")
def api_chefs_results():
    with chefs_lock:
        return jsonify(chefs_state["results"])


@app.route("/api/chefs/export/<fmt>")
def api_chefs_export(fmt):
    with chefs_lock:
        results = list(chefs_state["results"])

    if not results:
        return jsonify({"error": "Aucune donnée à exporter."}), 400

    df = pd.DataFrame(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fmt == "csv":
        filepath = os.path.join(DATA_DIR, f"chefs_etablissement_{timestamp}.csv")
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        return send_file(
            filepath,
            as_attachment=True,
            download_name=f"chefs_etablissement_{timestamp}.csv",
        )
    elif fmt == "excel":
        filepath = os.path.join(DATA_DIR, f"chefs_etablissement_{timestamp}.xlsx")
        df.to_excel(filepath, index=False)
        return send_file(
            filepath,
            as_attachment=True,
            download_name=f"chefs_etablissement_{timestamp}.xlsx",
        )
    else:
        return jsonify({"error": "Format non supporté. Utilisez 'csv' ou 'excel'."}), 400


if __name__ == "__main__":
    app.run(debug=True, port=5000)
