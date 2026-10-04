"""ArchiSearch : catalogue de bâtiments (Flask + SQLite).

  python server.py                 -> local, ouvre le navigateur
  python server.py --lan           -> accessible depuis le réseau
  python server.py --demo          -> (ré)ajoute les bâtiments d'exemple manquants
  python server.py --port 8080 --no-browser
"""
import argparse
import json
import socket
import sqlite3
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory

# Dossier de l'application (à côté de l'.exe une fois packagée) et des fichiers statiques
FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
STATIC_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "static"
DB_PATH = APP_DIR / "archisearch.db"

TYPES = ("Public", "Logement", "Industriel", "Culturel")
MAX = {"title": 120, "description": 1000, "url": 500, "tag": 30, "tags": 10}

DEMO = [
    dict(title="Centre Pompidou", type="Culturel", image="", tags=["high-tech", "acier", "1977"],
         description="Musée et bibliothèque à Paris, célèbre pour ses structures et conduits laissés apparents.",
         link="https://fr.wikipedia.org/wiki/Centre_Pompidou"),
    dict(title="Cité radieuse", type="Logement", image="", tags=["béton brut", "Le Corbusier", "1952"],
         description="Unité d'habitation de Le Corbusier à Marseille, pensée comme une petite ville verticale.",
         link="https://fr.wikipedia.org/wiki/Cit%C3%A9_radieuse"),
    dict(title="Bibliothèque nationale de France", type="Public", image="", tags=["verre", "tours", "1996"],
         description="Site François-Mitterrand de Dominique Perrault : quatre tours d'angle en forme de livres ouverts.",
         link="https://en.wikipedia.org/wiki/Biblioth%C3%A8que_nationale_de_France"),
    dict(title="Usine Fagus", type="Industriel", image="", tags=["Gropius", "façade vitrée", "1913"],
         description="Usine de formes à chaussures d'Alfeld, précurseur de l'architecture moderne, classée à l'UNESCO.",
         link="https://en.wikipedia.org/wiki/Fagus_Factory"),
]

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")


# ---------- Base de données ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def insert_building(db, b):
    cur = db.execute(
        "INSERT INTO buildings (title, type, image, description, tags, link) VALUES (?,?,?,?,?,?)",
        (b["title"], b["type"], b["image"], b["description"], json.dumps(b["tags"]), b["link"]))
    return cur.lastrowid


def add_demo(db):
    """Ajoute les bâtiments d'exemple absents (par titre) ; ne touche à rien d'autre."""
    for b in DEMO:
        if not db.execute("SELECT 1 FROM buildings WHERE title = ?", (b["title"],)).fetchone():
            insert_building(db, b)


def init_db(force_demo=False):
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS buildings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                type        TEXT NOT NULL,
                image       TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,
                tags        TEXT NOT NULL DEFAULT '[]',
                link        TEXT NOT NULL DEFAULT ''
            )""")
        # Les exemples ne sont semés qu'à la première création (puis sur demande avec --demo),
        # pour ne pas faire réapparaître ce que l'utilisateur a supprimé.
        if force_demo or db.execute("PRAGMA user_version").fetchone()[0] == 0:
            add_demo(db)
            db.execute("PRAGMA user_version = 1")


def row_to_dict(row):
    return {**dict(row), "tags": json.loads(row["tags"])}


# ---------- Validation ----------
def clean_text(value, limit):
    return str(value or "").strip()[:limit]


def is_http_url(value):
    return value == "" or value.startswith(("http://", "https://"))


def validate(data):
    """Retourne (données nettoyées, message d'erreur)."""
    if not isinstance(data, dict):
        return None, "Corps JSON invalide."
    b = {
        "title": clean_text(data.get("title"), MAX["title"]),
        "description": clean_text(data.get("description"), MAX["description"]),
        "type": data.get("type"),
        "image": clean_text(data.get("image"), MAX["url"]),
        "link": clean_text(data.get("link"), MAX["url"]),
    }
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        return None, "Les tags doivent être une liste."
    b["tags"] = [t for t in (clean_text(t, MAX["tag"]) for t in tags) if t][:MAX["tags"]]

    if not b["title"] or not b["description"]:
        return None, "Le nom et la description sont obligatoires."
    if b["type"] not in TYPES:
        return None, f"Type invalide (attendu : {', '.join(TYPES)})."
    if not (is_http_url(b["image"]) and is_http_url(b["link"])):  # refuse javascript: & co
        return None, "Les liens doivent commencer par http:// ou https://."
    return b, None


# ---------- API ----------
@app.get("/api/buildings")
def list_buildings():
    sql, args = "SELECT * FROM buildings", ()
    if request.args.get("type"):
        sql, args = sql + " WHERE type = ? COLLATE NOCASE", (request.args["type"],)
    rows = get_db().execute(sql + " ORDER BY id DESC", args).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.post("/api/buildings")
def create_building():
    clean, error = validate(request.get_json(silent=True))
    if error:
        return jsonify(error=error), 400
    db = get_db()
    new_id = insert_building(db, clean)
    db.commit()
    row = db.execute("SELECT * FROM buildings WHERE id = ?", (new_id,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.delete("/api/buildings/<int:building_id>")
def delete_building(building_id):
    db = get_db()
    deleted = db.execute("DELETE FROM buildings WHERE id = ?", (building_id,)).rowcount
    db.commit()
    return ("", 204) if deleted else (jsonify(error="Bâtiment introuvable."), 404)


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify(error="Route inconnue."), 404
    return "Page introuvable.", 404


@app.get("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


# ---------- Lancement ----------
def lan_ip():
    """Adresse IP de ce PC sur le réseau local (aucun paquet n'est envoyé)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def free_port(start):
    for port in range(start, start + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:  # rien n'écoute : le port est libre
                return port
    raise SystemExit(f"Aucun port libre entre {start} et {start + 19}.")


def main():
    parser = argparse.ArgumentParser(description="Serveur ArchiSearch")
    parser.add_argument("--lan", action="store_true", help="accessible depuis le réseau local")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true", help="n'ouvre pas le navigateur")
    parser.add_argument("--demo", action="store_true", help="réajoute les bâtiments d'exemple manquants")
    args = parser.parse_args()

    init_db(force_demo=args.demo)
    port = free_port(args.port)
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    url = f"http://127.0.0.1:{port}"

    print("\n  ArchiSearch est lancé. Fermez cette fenêtre pour l'arrêter.")
    print(f"  Sur ce PC       : {url}")
    if args.lan:
        print(f"  Sur un autre PC : http://{lan_ip()}:{port}")
    print(f"  Données         : {DB_PATH}\n")

    if not args.no_browser:
        threading.Timer(1, lambda: webbrowser.open(url)).start()

    try:
        from waitress import serve  # serveur adapté à l'usage réel, s'il est installé
    except ImportError:
        app.run(host=host, port=port, debug=False)
    else:
        serve(app, host=host, port=port)


if __name__ == "__main__":
    main()