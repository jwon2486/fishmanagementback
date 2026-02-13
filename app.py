from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# SQLite DB path (default: file next to app.py)
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(APP_DIR, "inventory.db"))

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)  # You can restrict origins later if desired.


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True) if os.path.dirname(DATABASE) else None
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fish TEXT NOT NULL,
            size TEXT NOT NULL,
            qty REAL NOT NULL DEFAULT 0,
            unit_price REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )
    conn.commit()
    conn.close()


@app.before_first_request
def _startup() -> None:
    init_db()


@app.get("/")
def index():
    # Serve the single-page app
    return send_from_directory(APP_DIR, "index.html")


# -----------------------
# Inventory API
# -----------------------

@app.get("/api/inventory")
def api_inventory_list():
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
          id, fish, size, qty, unit_price,
          ROUND(qty * unit_price, 2) AS amount,
          created_at
        FROM inventory
        ORDER BY id DESC
        """
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.post("/api/inventory")
def api_inventory_add():
    data = request.get_json(force=True) or {}
    fish = (data.get("fish") or "").strip()
    size = (data.get("size") or "").strip()

    try:
        qty = float(data.get("qty") or 0)
        unit_price = float(data.get("unit_price") or 0)
    except Exception:
        return jsonify({"error": "수량/단가는 숫자여야 합니다."}), 400

    if not fish or not size:
        return jsonify({"error": "어류/사이즈는 필수입니다."}), 400
    if qty < 0 or unit_price < 0:
        return jsonify({"error": "수량/단가는 0 이상이어야 합니다."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO inventory (fish, size, qty, unit_price)
        VALUES (?, ?, ?, ?)
        """,
        (fish, size, qty, unit_price),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"id": new_id}), 201


@app.put("/api/inventory/<int:item_id>")
def api_inventory_update(item_id: int):
    data = request.get_json(force=True) or {}
    fish = (data.get("fish") or "").strip()
    size = (data.get("size") or "").strip()

    try:
        qty = float(data.get("qty") or 0)
        unit_price = float(data.get("unit_price") or 0)
    except Exception:
        return jsonify({"error": "수량/단가는 숫자여야 합니다."}), 400

    if not fish or not size:
        return jsonify({"error": "어류/사이즈는 필수입니다."}), 400
    if qty < 0 or unit_price < 0:
        return jsonify({"error": "수량/단가는 0 이상이어야 합니다."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE inventory
        SET fish=?, size=?, qty=?, unit_price=?
        WHERE id=?
        """,
        (fish, size, qty, unit_price, item_id),
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()

    if updated == 0:
        return jsonify({"error": "해당 항목을 찾을 수 없습니다."}), 404

    return jsonify({"success": True}), 200


@app.delete("/api/inventory/<int:item_id>")
def api_inventory_delete(item_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM inventory WHERE id=?", (item_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    if deleted == 0:
        return jsonify({"error": "해당 항목을 찾을 수 없습니다."}), 404

    return jsonify({"success": True}), 200


@app.post("/api/inventory/bulk")
def api_inventory_bulk_update():
    data = request.get_json(force=True) or {}
    items = data.get("items") or []

    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"error": "items 리스트가 필요합니다."}), 400

    normalized: List[tuple] = []
    try:
        for it in items:
            item_id = int(it.get("id"))
            fish = (it.get("fish") or "").strip()
            size = (it.get("size") or "").strip()
            if not fish or not size:
                raise ValueError("어류/사이즈는 필수입니다.")
            qty = float(it.get("qty") or 0)
            unit_price = float(it.get("unit_price") or 0)
            if qty < 0 or unit_price < 0:
                raise ValueError("수량/단가는 0 이상이어야 합니다.")
            normalized.append((fish, size, qty, unit_price, item_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        for fish, size, qty, unit_price, item_id in normalized:
            cur.execute(
                """
                UPDATE inventory
                SET fish=?, size=?, qty=?, unit_price=?
                WHERE id=?
                """,
                (fish, size, qty, unit_price, item_id),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"bulk update 실패: {e}"}), 500
    finally:
        conn.close()

    return jsonify({"success": True, "updated": len(normalized)}), 200


if __name__ == "__main__":
    init_db()
    # For local development only
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
