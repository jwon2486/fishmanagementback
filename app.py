from __future__ import annotations

import os
import sqlite3
import calendar
import sqlite3
import pandas as pd
import os
import re
import shutil  # ✅ DB 파일 복사용
import xmltodict
import requests
import ssl
from requests.adapters import HTTPAdapter
import base64
import threading
import time
from typing import List
from flask import Flask, jsonify, request, send_from_directory, send_file, abort
from flask_cors import CORS

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(APP_DIR, "fishdb.sqlite")

# ✅ Flask 단 한번만 생성
app = Flask(__name__, static_folder=".", static_url_path="")

# ✅ CORS 확실히 허용 (프리플라이트 포함)
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# -----------------------
# DB
# -----------------------
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fish TEXT NOT NULL,
            size TEXT NOT NULL,
            qty REAL NOT NULL DEFAULT 0,
            unit_price REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()

init_db()

# -----------------------
# Front
# -----------------------
@app.get("/")
def index():
    return "Flask 서버 정상 가동중"

# -----------------------
# Inventory API
# -----------------------

@app.get("/api/inventory")
def api_inventory_list():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT id, fish, size, qty, unit_price,
               ROUND(qty * unit_price,2) AS amount,
               created_at
        FROM inventory
        ORDER BY id DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/inventory")
def api_inventory_add():
    data = request.get_json(force=True) or {}
    fish = (data.get("fish") or "").strip()
    size = (data.get("size") or "").strip()
    qty = float(data.get("qty") or 0)
    unit_price = float(data.get("unit_price") or 0)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO inventory (fish,size,qty,unit_price) VALUES (?,?,?,?)",
        (fish,size,qty,unit_price)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    return jsonify({"id": new_id}),201

@app.put("/api/inventory/<int:item_id>")
def api_inventory_update(item_id):
    data = request.get_json(force=True) or {}
    fish = (data.get("fish") or "").strip()
    size = (data.get("size") or "").strip()
    qty = float(data.get("qty") or 0)
    unit_price = float(data.get("unit_price") or 0)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE inventory
        SET fish=?, size=?, qty=?, unit_price=?
        WHERE id=?
    """,(fish,size,qty,unit_price,item_id))
    conn.commit()
    conn.close()

    return jsonify({"success":True})

@app.delete("/api/inventory/<int:item_id>")
def api_inventory_delete(item_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM inventory WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({"success":True})

@app.post("/api/inventory/bulk")
def api_inventory_bulk():
    data = request.get_json(force=True) or {}
    items = data.get("items") or []

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("BEGIN")

    for it in items:
        cur.execute("""
            UPDATE inventory
            SET fish=?, size=?, qty=?, unit_price=?
            WHERE id=?
        """,(it["fish"],it["size"],it["qty"],it["unit_price"],it["id"]))

    conn.commit()
    conn.close()
    return jsonify({"success":True,"updated":len(items)})


@app.get("/api/db/download")
def download_db():
    # ✅ (권장) 간단 보호: 환경변수 DB_DOWNLOAD_KEY 설정 시 키 없으면 차단
    required_key = os.environ.get("DB_DOWNLOAD_KEY", "").strip()
    if required_key:
        key = (request.args.get("key") or "").strip()
        if key != required_key:
            return jsonify({"error": "unauthorized"}), 401

    # ✅ DB가 사용 중일 수 있으니 복사본을 만들어 내려줌
    src = DATABASE
    if not os.path.exists(src):
        return jsonify({"error": "db file not found"}), 404

    tmp = os.path.join(APP_DIR, "fishdb_download.sqlite")
    try:
        shutil.copy2(src, tmp)

        # ✅ 다운로드로 보내기
        return send_file(
            tmp,
            as_attachment=True,
            download_name="fishdb.sqlite",
            mimetype="application/octet-stream",
            conditional=True,  # 브라우저 캐시/재개 다운로드에 도움
        )
    finally:
        # ✅ 응답 후 바로 삭제하고 싶으면 여기서 지우면 안 됩니다(전송 중 삭제 위험)
        # 대신 Render는 재시작/재배포 시 파일이 정리되기도 해서,
        # 즉시 삭제가 필요하면 별도 스레드/딜레이 삭제 방식 사용.
        pass

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5000,debug=True)