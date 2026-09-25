import csv
import io
import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, Response, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "chemical_monitor.db")
AUDIT_LOG = os.path.join(BASE_DIR, "audit_log.jsonl")
DATE_FORMAT = "%Y-%m-%d"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production-2026")

DEFAULT_USERS = {
    "admin": {"password": "admin123", "role": "System Admin"},
    "custodian": {"password": "lab123", "role": "Laboratory Custodian"},
    "staff": {"password": "lab123", "role": "Laboratory Staff"},
    "dept": {"password": "dept123", "role": "Department Head"},
}

ROLES = {
    "System Admin": {"add", "edit", "delete", "request", "update_status", "view_reports", "view_audit"},
    "Laboratory Custodian": {"add", "edit", "delete", "request", "view_reports", "view_audit"},
    "Laboratory Staff": {"request", "view_reports"},
    "Department Head": {"update_status", "view_reports", "view_audit"},
}

ROLE_COLORS = {
    "System Admin": "#0b5394",
    "Laboratory Custodian": "#7c3aed",
    "Laboratory Staff": "#2e7d32",
    "Department Head": "#d97706",
}


def has_permission(action):
    return action in ROLES.get(session.get("role", ""), set())


def current_user():
    return {"username": session.get("username", ""), "role": session.get("role", "")}


def log_action(action, details=""):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": session.get("username", "anonymous"),
        "role": session.get("role", "anonymous"),
        "action": action,
        "details": details,
    }
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = connect_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chemicals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chemical_name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'units',
            hazard_category TEXT NOT NULL DEFAULT 'General',
            supplier TEXT DEFAULT '',
            batch_number TEXT DEFAULT '',
            expiry_date TEXT NOT NULL,
            room TEXT DEFAULT '',
            cabinet TEXT DEFAULT '',
            shelf TEXT DEFAULT '',
            safety_notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS disposal_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chemical_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            request_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            approved_by TEXT DEFAULT '',
            completed_date TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            FOREIGN KEY (chemical_id) REFERENCES chemicals(id) ON DELETE CASCADE
        );
        """
    )
    if conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0:
        for username, info in DEFAULT_USERS.items():
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(info["password"]), info["role"]),
            )
    conn.commit()
    conn.close()


def parse_date(value):
    return datetime.strptime(value.strip(), DATE_FORMAT).date()


def expiry_status(expiry_date, today=None):
    today = today or date.today()
    try:
        expiry = parse_date(expiry_date)
    except ValueError:
        return "Invalid date"
    if expiry < today:
        return "Expired"
    if expiry <= today + timedelta(days=30):
        return "Expiring soon"
    return "Valid"


def seed_demo_data():
    conn = connect_db()
    count = conn.execute("SELECT COUNT(*) AS c FROM chemicals").fetchone()["c"]
    if count:
        conn.close()
        return False
    today = date.today()
    rows = [
        ("Sodium Chloride Solution", 15, "bottles", "General", "Lab Supply Co.", "SC-2026-01", (today + timedelta(days=240)).isoformat(), "Science Lab 1", "Cabinet A", "Shelf 2", "For laboratory demonstration only."),
        ("Hydrogen Peroxide", 4, "bottles", "Oxidizer", "EduChem Supplies", "HP-2025-11", (today + timedelta(days=18)).isoformat(), "Science Lab 1", "Cabinet B", "Shelf 1", "Keep away from heat and incompatible materials."),
        ("Copper Sulfate", 2.5, "kg", "Irritant", "School Laboratory Store", "CS-2024-09", (today - timedelta(days=12)).isoformat(), "Science Lab 2", "Cabinet C", "Shelf 3", "For authorized laboratory activities."),
    ]
    conn.executemany(
        """INSERT INTO chemicals
        (chemical_name, quantity, unit, hazard_category, supplier, batch_number, expiry_date, room, cabinet, shelf, safety_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows
    )
    conn.commit()
    conn.close()
    return True


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def permission_required(action):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not has_permission(action):
                flash("Your role does not have permission for that action.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/")
def index():
    if session.get("username"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        conn = connect_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["username"] = user["username"]
            session["role"] = user["role"]
            log_action("login")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    log_action("logout")
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = connect_db()
    rows = conn.execute("SELECT expiry_date FROM chemicals").fetchall()
    pending = conn.execute("SELECT COUNT(*) AS c FROM disposal_requests WHERE status = 'Pending'").fetchone()["c"]
    conn.close()
    stats = {
        "total": len(rows),
        "expired": sum(expiry_status(r["expiry_date"]) == "Expired" for r in rows),
        "soon": sum(expiry_status(r["expiry_date"]) == "Expiring soon" for r in rows),
        "pending": pending,
    }
    return render_template("dashboard.html", stats=stats, user=current_user())


@app.route("/chemicals")
@login_required
def chemicals():
    search = request.args.get("q", "").strip()
    conn = connect_db()
    if search:
        like = f"%{search}%"
        rows = conn.execute(
            """SELECT * FROM chemicals WHERE chemical_name LIKE ? OR hazard_category LIKE ?
               OR room LIKE ? OR cabinet LIKE ? OR batch_number LIKE ? ORDER BY expiry_date""",
            (like, like, like, like, like),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM chemicals ORDER BY expiry_date").fetchall()
    conn.close()
    items = []
    for row in rows:
        item = dict(row)
        item["status"] = expiry_status(row["expiry_date"])
        item["location"] = " / ".join(x for x in [row["room"], row["cabinet"], row["shelf"]] if x)
        items.append(item)
    return render_template("chemicals.html", items=items, search=search, user=current_user())


@app.route("/chemicals/add", methods=["GET", "POST"])
@login_required
@permission_required("add")
def add_chemical():
    if request.method == "POST":
        values = {k: request.form.get(k, "").strip() for k in
                  ["chemical_name", "quantity", "unit", "hazard_category", "supplier",
                   "batch_number", "expiry_date", "room", "cabinet", "shelf", "safety_notes"]}
        if not values["chemical_name"] or not values["expiry_date"]:
            flash("Chemical name and expiry date are required.", "danger")
            return render_template("chemical_form.html", item=None, user=current_user())
        try:
            values["quantity"] = float(values["quantity"] or 0)
            parse_date(values["expiry_date"])
        except ValueError:
            flash("Quantity must be a number and expiry date must use YYYY-MM-DD.", "danger")
            return render_template("chemical_form.html", item=None, user=current_user())
        conn = connect_db()
        conn.execute(
            """INSERT INTO chemicals (chemical_name, quantity, unit, hazard_category, supplier,
               batch_number, expiry_date, room, cabinet, shelf, safety_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(values[k] for k in ["chemical_name", "quantity", "unit", "hazard_category",
                                      "supplier", "batch_number", "expiry_date", "room", "cabinet",
                                      "shelf", "safety_notes"]),
        )
        conn.commit()
        conn.close()
        log_action("add_chemical", f"Added chemical: {values['chemical_name']}")
        flash("Chemical record saved.", "success")
        return redirect(url_for("chemicals"))
    return render_template("chemical_form.html", item=None, user=current_user())


@app.route("/chemicals/<int:chemical_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("edit")
def edit_chemical(chemical_id):
    conn = connect_db()
    existing = conn.execute("SELECT * FROM chemicals WHERE id = ?", (chemical_id,)).fetchone()
    if not existing:
        conn.close()
        flash("Chemical not found.", "danger")
        return redirect(url_for("chemicals"))
    if request.method == "POST":
        values = {k: request.form.get(k, "").strip() for k in
                  ["chemical_name", "quantity", "unit", "hazard_category", "supplier",
                   "batch_number", "expiry_date", "room", "cabinet", "shelf", "safety_notes"]}
        try:
            values["quantity"] = float(values["quantity"] or 0)
            parse_date(values["expiry_date"])
        except ValueError:
            conn.close()
            flash("Quantity must be a number and expiry date must use YYYY-MM-DD.", "danger")
            return render_template("chemical_form.html", item=existing, user=current_user())
        conn.execute(
            """UPDATE chemicals SET chemical_name=?, quantity=?, unit=?, hazard_category=?,
               supplier=?, batch_number=?, expiry_date=?, room=?, cabinet=?, shelf=?,
               safety_notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            tuple(values[k] for k in ["chemical_name", "quantity", "unit", "hazard_category",
                                      "supplier", "batch_number", "expiry_date", "room", "cabinet",
                                      "shelf", "safety_notes"]) + (chemical_id,),
        )
        conn.commit()
        conn.close()
        log_action("edit_chemical", f"Edited chemical ID {chemical_id}: {values['chemical_name']}")
        flash("Chemical record updated.", "success")
        return redirect(url_for("chemicals"))
    conn.close()
    return render_template("chemical_form.html", item=existing, user=current_user())


@app.route("/chemicals/<int:chemical_id>/delete", methods=["POST"])
@login_required
@permission_required("delete")
def delete_chemical(chemical_id):
    conn = connect_db()
    name = conn.execute("SELECT chemical_name FROM chemicals WHERE id = ?", (chemical_id,)).fetchone()
    conn.execute("DELETE FROM chemicals WHERE id = ?", (chemical_id,))
    conn.commit()
    conn.close()
    log_action("delete_chemical", f"Deleted chemical ID {chemical_id}: {name['chemical_name'] if name else ''}")
    flash("Chemical record deleted.", "success")
    return redirect(url_for("chemicals"))


@app.route("/disposals")
@login_required
def disposals():
    conn = connect_db()
    rows = conn.execute(
        """SELECT d.*, c.chemical_name FROM disposal_requests d
           JOIN chemicals c ON c.id = d.chemical_id
           ORDER BY CASE d.status WHEN 'Pending' THEN 0 ELSE 1 END, d.request_date DESC, d.id DESC"""
    ).fetchall()
    conn.close()
    return render_template("disposals.html", items=rows, user=current_user())


@app.route("/disposals/add", methods=["GET", "POST"])
@login_required
@permission_required("request")
def add_disposal():
    conn = connect_db()
    chemicals = conn.execute("SELECT id, chemical_name, expiry_date FROM chemicals ORDER BY chemical_name").fetchall()
    conn.close()
    if not chemicals:
        flash("Add a chemical record before creating a disposal request.", "warning")
        return redirect(url_for("chemicals"))
    if request.method == "POST":
        chemical_id = request.form.get("chemical_id")
        reason = request.form.get("reason", "").strip()
        requested_by = request.form.get("requested_by", "").strip()
        request_date = request.form.get("request_date", "").strip()
        notes = request.form.get("notes", "").strip()
        if not chemical_id or not reason or not requested_by:
            flash("Chemical, reason, and requested by are required.", "danger")
            return render_template("disposal_form.html", chemicals=chemicals, item=None, user=current_user())
        try:
            parse_date(request_date)
        except ValueError:
            flash("Request date must use YYYY-MM-DD.", "danger")
            return render_template("disposal_form.html", chemicals=chemicals, item=None, user=current_user())
        conn = connect_db()
        conn.execute(
            "INSERT INTO disposal_requests (chemical_id, reason, requested_by, request_date, status, notes) VALUES (?, ?, ?, ?, 'Pending', ?)",
            (chemical_id, reason, requested_by, request_date, notes),
        )
        conn.commit()
        conn.close()
        log_action("create_disposal_request", f"Request for chemical ID {chemical_id}: {reason}")
        flash("Disposal request created.", "success")
        return redirect(url_for("disposals"))
    return render_template("disposal_form.html", chemicals=chemicals, item=None, user=current_user())


@app.route("/disposals/<int:request_id>/update", methods=["GET", "POST"])
@login_required
@permission_required("update_status")
def update_disposal(request_id):
    conn = connect_db()
    existing = conn.execute(
        """SELECT d.*, c.chemical_name FROM disposal_requests d
           JOIN chemicals c ON c.id = d.chemical_id WHERE d.id = ?""", (request_id,)
    ).fetchone()
    if not existing:
        conn.close()
        flash("Disposal request not found.", "danger")
        return redirect(url_for("disposals"))
    if request.method == "POST":
        status = request.form.get("status", "Pending")
        approved_by = request.form.get("approved_by", "").strip()
        completed_date = request.form.get("completed_date", "").strip()
        notes = request.form.get("notes", "").strip()
        if status in ("Approved", "Completed") and not approved_by:
            conn.close()
            flash("Approved by is required for approved or completed requests.", "danger")
            return render_template("disposal_form.html", chemicals=[], item=existing, user=current_user())
        if completed_date:
            try:
                parse_date(completed_date)
            except ValueError:
                conn.close()
                flash("Completed date must use YYYY-MM-DD.", "danger")
                return render_template("disposal_form.html", chemicals=[], item=existing, user=current_user())
        conn.execute(
            "UPDATE disposal_requests SET status=?, approved_by=?, completed_date=?, notes=? WHERE id=?",
            (status, approved_by, completed_date, notes, request_id),
        )
        conn.commit()
        conn.close()
        log_action("update_disposal_request", f"Request ID {request_id} status changed to {status} (approved by {approved_by or 'n/a'})")
        flash("Disposal request updated.", "success")
        return redirect(url_for("disposals"))
    conn.close()
    return render_template("disposal_form.html", chemicals=[], item=existing, user=current_user())


@app.route("/reports")
@login_required
@permission_required("view_reports")
def reports():
    conn = connect_db()
    chemicals = conn.execute("SELECT * FROM chemicals ORDER BY expiry_date").fetchall()
    disposals = conn.execute(
        """SELECT d.*, c.chemical_name FROM disposal_requests d
           JOIN chemicals c ON c.id = d.chemical_id ORDER BY d.request_date DESC"""
    ).fetchall()
    conn.close()
    inventory = [dict(r) for r in chemicals]
    expiry = []
    for row in chemicals:
        item = dict(row)
        item["status"] = expiry_status(row["expiry_date"])
        expiry.append(item)
    return render_template("reports.html", inventory=inventory, expiry=expiry,
                           disposals=[dict(r) for r in disposals], user=current_user())


@app.route("/reports/download/<report_type>")
@login_required
@permission_required("view_reports")
def download_report(report_type):
    conn = connect_db()
    if report_type == "inventory":
        rows = conn.execute("SELECT * FROM chemicals ORDER BY expiry_date").fetchall()
        name = "chemical_inventory.csv"
    elif report_type == "expiry":
        rows = conn.execute("SELECT * FROM chemicals ORDER BY expiry_date").fetchall()
        name = "expiry_monitoring_report.csv"
    elif report_type == "disposals":
        rows = conn.execute(
            """SELECT d.*, c.chemical_name FROM disposal_requests d
               JOIN chemicals c ON c.id = d.chemical_id ORDER BY d.request_date DESC"""
        ).fetchall()
        name = "disposal_requests_report.csv"
    else:
        conn.close()
        flash("Unknown report type.", "danger")
        return redirect(url_for("reports"))
    conn.close()
    data = []
    for row in rows:
        item = dict(row)
        if report_type == "expiry":
            item["status"] = expiry_status(item["expiry_date"])
        data.append(item)
    if not data:
        flash("No records to export.", "warning")
        return redirect(url_for("reports"))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(data[0].keys()))
    writer.writeheader()
    writer.writerows(data)
    log_action("export_csv", f"Exported {name} ({len(data)} rows)")
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}"},
    )


@app.route("/audit")
@login_required
@permission_required("view_audit")
def audit():
    entries = []
    if os.path.exists(AUDIT_LOG):
        with open(AUDIT_LOG, encoding="utf-8") as f:
            lines = f.readlines()[-300:]
        for line in reversed(lines):
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return render_template("audit.html", entries=entries, user=current_user())


@app.route("/demo", methods=["POST"])
@login_required
def load_demo():
    if seed_demo_data():
        log_action("load_demo_data", "Sample chemical records added")
        flash("Demo data added.", "success")
    else:
        flash("Demo data can only be added when the chemical list is empty.", "warning")
    return redirect(url_for("dashboard"))


@app.context_processor
def inject_globals():
    return {
        "has_permission": has_permission,
        "current_user": current_user,
        "role_colors": ROLE_COLORS,
    }


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
