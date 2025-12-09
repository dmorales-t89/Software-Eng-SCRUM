from flask import Flask, render_template, request, redirect, url_for, session
import json
import os
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "change-this-secret"  # needed for sessions

DATA_FILE = "complaints.json"

# Fake employee "database"
USERS = {
    "dispatcher": {"password": "dispatch123", "role": "dispatcher"},
    "safety": {"password": "safety123", "role": "safety_director"},
}

truck_drivers = {
    "101": "Bob Smith",
    "102": "Bob Smith",
    "106": "Bob Smith",
    "103": "Alice Johnson",
    "107": "Alice Johnson",
    "104": "Charlie Brown",
    "108": "Charlie Brown",
    "109": "Eve Davis",
    "110": "Eve Davis",
    "105": "Diana Prince"
}


# Helper functions
def load_complaints():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_complaints(complaints):
    with open(DATA_FILE, "w") as f:
        json.dump(complaints, f, indent=4)


def is_employee_logged_in():
    return session.get("role") in ("dispatcher", "safety_director")


# Routes
@app.route("/")
def index():
    return render_template("index.html")


# ---------- EMPLOYEE-ONLY ROUTES ----------

@app.route("/complaints")
def complaints():
    if not is_employee_logged_in():
        return redirect(url_for("login"))

    data = load_complaints()

    # Build nested structure: driver -> truck -> [complaints]
    complaints_by_driver = defaultdict(lambda: defaultdict(list))
    for c in data:
        truck_key = c.get("truck", "Unknown")
        driver_name = truck_drivers.get(truck_key, "Unknown Driver")
        complaints_by_driver[driver_name][truck_key].append(c)

    # Convert to normal dicts (optional but easier in templates)
    complaints_by_driver = {
        driver: dict(trucks) for driver, trucks in complaints_by_driver.items()
    }

    # Compute totals per driver (sum of complaints across that driver's trucks)
    driver_totals = {}
    driver_flagged = {}
    for driver, trucks in complaints_by_driver.items():
        total = 0
        for truck, clist in trucks.items():
            total += len(clist)
        driver_totals[driver] = total
        driver_flagged[driver] = total >= 2

    return render_template(
        "complaints.html",
        complaints_by_driver=complaints_by_driver,
        driver_totals=driver_totals,
        driver_flagged=driver_flagged,
        truck_drivers=truck_drivers
    )


@app.route("/complaint/<int:id>")
def view_complaints(id):
    if not is_employee_logged_in():
        return redirect(url_for("login"))

    data = load_complaints()
    comp = next((c for c in data if c["id"] == id), None)
    return render_template("view_complaints.html", complaint=comp, truck_drivers=truck_drivers)


@app.route("/remove/<int:id>")
def remove_complaint(id):
    if not is_employee_logged_in():
        return redirect(url_for("login"))

    data = load_complaints()
    data = [c for c in data if c["id"] != id]
    save_complaints(data)
    return redirect(url_for("complaints"))


@app.route("/approve/<int:id>")
def approve_complaint(id):
    if not is_employee_logged_in():
        return redirect(url_for("login"))

    data = load_complaints()
    for c in data:
        if c["id"] == id:
            c["status"] = "Approved"

    save_complaints(data)
    return redirect(url_for("view_complaints", id=id))


@app.route("/summary")
def summary_report():
    if not is_employee_logged_in():
        return redirect(url_for("login"))

    data = load_complaints()

    total_complaints = len(data)
    needs_review = len([c for c in data if c["status"] == "Needs Review"])
    approved = len([c for c in data if c["status"] == "Approved"])
    flagged_complaints = len([c for c in data if c.get("flagged", False)])

    # Build driver statistics
    complaints_by_driver = defaultdict(lambda: defaultdict(list))
    for c in data:
        truck_key = c.get("truck", "Unknown")
        driver_name = truck_drivers.get(truck_key, "Unknown Driver")
        complaints_by_driver[driver_name][truck_key].append(c)

    # Convert to normal dicts
    complaints_by_driver = {
        driver: dict(trucks) for driver, trucks in complaints_by_driver.items()
    }

    # Driver stats
    driver_stats = []
    for driver, trucks in complaints_by_driver.items():
        total = sum(len(clist) for clist in trucks.values())
        driver_needs_review = sum(
            len([c for c in clist if c.get("status") == "Needs Review"])
            for clist in trucks.values()
        )
        driver_approved = sum(
            len([c for c in clist if c.get("status") == "Approved"])
            for clist in trucks.values()
        )
        driver_flagged = total >= 2

        driver_stats.append({
            "name": driver,
            "total": total,
            "needs_review": driver_needs_review,
            "approved": driver_approved,
            "flagged": driver_flagged,
            "trucks": len(trucks)
        })

    # Sort by total complaints (descending)
    driver_stats.sort(key=lambda x: x["total"], reverse=True)

    return render_template(
        "summary_report.html",
        total_complaints=total_complaints,
        needs_review=needs_review,
        approved=approved,
        flagged_complaints=flagged_complaints,
        driver_stats=driver_stats
    )


# ---------- PUBLIC ROUTES (CIVILIANS) ----------

@app.route("/new", methods=["GET", "POST"])
def new_complaint():
    if request.method == "POST":
        data = load_complaints()

        new_id = 1 if len(data) == 0 else data[-1]["id"] + 1

        complaint = {
            "id": new_id,
            "truck": request.form["truck"],
            "street": request.form["street"],
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": request.form["time"],
            "description": request.form["description"],
            "contact": request.form.get("contact", ""),
            "status": "Needs Review",
            "flagged": False
        }

        data.append(complaint)

        # Auto-flag trucks with 2 or more complaints
        truck_key = complaint["truck"]
        truck_complaints = [c for c in data if c.get("truck") == truck_key]
        if len(truck_complaints) >= 2:
            for c in truck_complaints:
                c["flagged"] = True

        save_complaints(data)
        return redirect(url_for("index"))

    return render_template("new_complaint.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/faq")
def faq():
    return render_template("faq.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


# ---------- AUTH ROUTES ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = USERS.get(username)
        if user and user["password"] == password:
            session["user"] = username
            session["role"] = user["role"]
            return redirect(url_for("complaints"))
        else:
            error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
