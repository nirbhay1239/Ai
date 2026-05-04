"""
TradeBrainX — Angel One SmartAPI Proxy
=======================================
Upload this file to PythonAnywhere as: /home/NDJ1239/angel_proxy.py
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import pyotp
import time

app = Flask(__name__)
CORS(app, origins="*")  # Allow all origins (your HTML app)

BASE_URL = "https://apiconnect.angelone.in"

# In-memory session store
session = {
    "jwt_token":     None,
    "refresh_token": None,
    "feed_token":    None,
    "api_key":       None,
    "client_id":     None,
    "logged_in":     False,
    "login_time":    None,
    "name":          "",
}


# ── Health check ────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": True,
        "message": "TradeBrainX Angel One Proxy is running ✅",
        "logged_in": session["logged_in"],
    })


# ── Status ──────────────────────────────────────────────────
@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status":    True,
        "logged_in": session["logged_in"],
        "client_id": session["client_id"],
        "name":      session["name"],
    })


# ── Login ───────────────────────────────────────────────────
@app.route("/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return _cors_preflight()

    body        = request.get_json() or {}
    api_key     = body.get("api_key", "").strip()
    client_id   = body.get("client_id", "").strip()
    mpin        = body.get("mpin", "").strip()
    totp_secret = body.get("totp_secret", "").strip()

    if not all([api_key, client_id, mpin, totp_secret]):
        return jsonify({"status": False, "message": "All 4 fields required: api_key, client_id, mpin, totp_secret"}), 400

    # Generate live TOTP
    try:
        totp = pyotp.TOTP(totp_secret).now()
    except Exception as e:
        return jsonify({"status": False, "message": f"Invalid TOTP secret: {e}"}), 400

    # Call Angel One
    try:
        resp = requests.post(
            f"{BASE_URL}/rest/auth/angelbroking/user/v1/loginByPassword",
            headers={
                "Content-Type":     "application/json",
                "Accept":           "application/json",
                "X-APIKey":         api_key,
                "X-ClientID":       client_id,
                "X-SourceID":       "WEB",
                "X-UserType":       "USER",
                "X-ClientLocalIP":  "192.168.1.1",
                "X-ClientPublicIP": "106.0.0.1",
                "X-MACAddress":     "fe80::216e:6507:4b90:3719",
            },
            json={
                "clientcode": client_id,
                "password":   mpin,
                "totp":       totp,
            },
            timeout=15,
        )
        data = resp.json()
    except requests.exceptions.ConnectionError:
        return jsonify({"status": False, "message": "Cannot reach Angel One API. Check if your PythonAnywhere plan allows external requests."}), 502
    except Exception as e:
        return jsonify({"status": False, "message": f"Network error: {e}"}), 502

    if data.get("status") and data.get("data"):
        d = data["data"]
        session.update({
            "jwt_token":     d.get("jwtToken", ""),
            "refresh_token": d.get("refreshToken", ""),
            "feed_token":    d.get("feedToken", ""),
            "api_key":       api_key,
            "client_id":     client_id,
            "logged_in":     True,
            "login_time":    time.time(),
            "name":          d.get("name", client_id),
        })
        return jsonify({
            "status":  True,
            "message": f"Connected! Welcome {session['name']}",
            "data": {
                "name":       session["name"],
                "client_id":  client_id,
                "feed_token": session["feed_token"],
            }
        })
    else:
        msg = data.get("message", "Login failed. Check your credentials.")
        return jsonify({"status": False, "message": msg}), 401


# ── Place Order ─────────────────────────────────────────────
@app.route("/order", methods=["POST", "OPTIONS"])
def place_order():
    if request.method == "OPTIONS":
        return _cors_preflight()
    if not session["logged_in"]:
        return jsonify({"status": False, "message": "Not logged in"}), 401

    body       = request.get_json() or {}
    symbol     = body.get("symbol", "")
    token      = body.get("token", "3045")
    side       = body.get("side", "LONG")
    qty        = str(body.get("qty", 1))
    order_type = body.get("order_type", "MARKET")
    price      = str(body.get("price", 0))
    sl_price   = str(body.get("sl_price", 0))
    transaction = "BUY" if side == "LONG" else "SELL"

    try:
        resp = requests.post(
            f"{BASE_URL}/rest/secure/angelbroking/order/v1/placeOrder",
            headers={
                "Authorization": f"Bearer {session['jwt_token']}",
                "Content-Type":  "application/json",
                "Accept":        "application/json",
                "X-APIKey":      session["api_key"],
                "X-ClientID":    session["client_id"],
                "X-SourceID":    "WEB",
                "X-UserType":    "USER",
            },
            json={
                "variety":         "NORMAL",
                "tradingsymbol":   symbol,
                "symboltoken":     token,
                "transactiontype": transaction,
                "exchange":        "NSE",
                "ordertype":       order_type,
                "producttype":     "INTRADAY",
                "duration":        "DAY",
                "price":           price,
                "triggerprice":    "0",
                "quantity":        qty,
                "squareoff":       "0",
                "stoploss":        sl_price,
            },
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        return jsonify({"status": False, "message": str(e)}), 502

    if data.get("status"):
        order_id = data.get("data", {}).get("orderid", "")
        return jsonify({"status": True, "order_id": order_id, "message": f"Order placed: {order_id}"})
    return jsonify({"status": False, "message": data.get("message", "Order failed")}), 400


# ── Positions ───────────────────────────────────────────────
@app.route("/positions", methods=["GET"])
def get_positions():
    if not session["logged_in"]:
        return jsonify({"status": False, "message": "Not logged in"}), 401
    try:
        resp = requests.get(
            f"{BASE_URL}/rest/secure/angelbroking/order/v1/getPosition",
            headers=_auth_headers(), timeout=15,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"status": False, "message": str(e)}), 502


# ── Funds ───────────────────────────────────────────────────
@app.route("/funds", methods=["GET"])
def get_funds():
    if not session["logged_in"]:
        return jsonify({"status": False, "message": "Not logged in"}), 401
    try:
        resp = requests.get(
            f"{BASE_URL}/rest/secure/angelbroking/user/v1/getRMS",
            headers=_auth_headers(), timeout=15,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"status": False, "message": str(e)}), 502


# ── Cancel Order ────────────────────────────────────────────
@app.route("/cancel", methods=["POST", "OPTIONS"])
def cancel_order():
    if request.method == "OPTIONS":
        return _cors_preflight()
    if not session["logged_in"]:
        return jsonify({"status": False, "message": "Not logged in"}), 401
    body     = request.get_json() or {}
    order_id = body.get("order_id", "")
    try:
        resp = requests.post(
            f"{BASE_URL}/rest/secure/angelbroking/order/v1/cancelOrder",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            json={"variety": "NORMAL", "orderid": order_id},
            timeout=15,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"status": False, "message": str(e)}), 502


# ── Logout ──────────────────────────────────────────────────
@app.route("/logout", methods=["POST"])
def logout():
    try:
        requests.post(
            f"{BASE_URL}/rest/secure/angelbroking/user/v1/logout",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            json={"clientcode": session["client_id"]},
            timeout=10,
        )
    except Exception:
        pass
    session.update({k: None for k in ["jwt_token","refresh_token","feed_token","api_key","client_id","login_time","name"]})
    session["logged_in"] = False
    return jsonify({"status": True, "message": "Logged out"})


# ── Helpers ─────────────────────────────────────────────────
def _auth_headers():
    return {
        "Authorization": f"Bearer {session['jwt_token']}",
        "Accept":        "application/json",
        "X-APIKey":      session["api_key"],
        "X-ClientID":    session["client_id"],
        "X-SourceID":    "WEB",
        "X-UserType":    "USER",
    }

def _cors_preflight():
    from flask import Response
    r = Response()
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return r, 200


# ── Run locally (not used on PythonAnywhere) ────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  TradeBrainX Proxy — http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
