from flask import Flask, request, jsonify
from flask_cors import CORS
import requests, pyotp
app = Flask(__name__)
CORS(app)
s = {"jwt":None,"key":None,"cid":None,"on":False,"name":""}
@app.route("/")
def home():
    return jsonify({"status":True,"message":"TradeBrainX Angel One Proxy is running"})
@app.route("/status")
def status():
    return jsonify({"status":True,"logged_in":s["on"],"client_id":s["cid"]})
@app.route("/login", methods=["POST","OPTIONS"])
def login():
    if request.method=="OPTIONS":
        return "",200
    b=request.get_json() or {}
    try:
        totp=pyotp.TOTP(b["totp_secret"]).now()
        r=requests.post("https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword",
            headers={"Content-Type":"application/json","X-APIKey":b["api_key"],"X-PrivateKey":b["api_key"],"X-ClientID":b["client_id"],"X-SourceID":"WEB","X-UserType":"USER","X-ClientLocalIP":"192.168.1.1","X-ClientPublicIP":"106.0.0.1","X-MACAddress":"fe80::216e:6507:4b90:3719"},
            json={"clientcode":b["client_id"],"password":b["mpin"],"totp":totp},timeout=15)
        d=r.json()
        if d.get("status"):
            s.update({"jwt":d["data"]["jwtToken"],"key":b["api_key"],"cid":b["client_id"],"on":True,"name":d["data"].get("name","")})
            return jsonify({"status":True,"message":f"Connected! Welcome {s['name']}","data":{"name":s["name"]}})
        return jsonify({"status":False,"message":d.get("message","Login failed")}),401
    except Exception as e:
        return jsonify({"status":False,"message":str(e)}),500
@app.route("/order", methods=["POST","OPTIONS"])
def order():
    if request.method=="OPTIONS":
        return "",200
    if not s["on"]:
        return jsonify({"status":False,"message":"Not logged in"}),401
    b=request.get_json() or {}
    try:
        r=requests.post("https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder",
            headers={"Authorization":f"Bearer {s['jwt']}","Content-Type":"application/json","X-APIKey":s["key"],"X-PrivateKey":s["key"],"X-ClientID":s["cid"],"X-SourceID":"WEB","X-UserType":"USER","X-ClientLocalIP":"192.168.1.1","X-ClientPublicIP":"106.0.0.1","X-MACAddress":"fe80::216e:6507:4b90:3719"},
            json={"variety":"NORMAL","tradingsymbol":b.get("symbol",""),"symboltoken":b.get("token","3045"),"transactiontype":"BUY" if b.get("side")=="LONG" else "SELL","exchange":"NSE","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","price":"0","triggerprice":"0","quantity":str(b.get("qty",1))},timeout=15)
        d=r.json()
        if d.get("status"):
            return jsonify({"status":True,"order_id":d["data"]["orderid"]})
        return jsonify({"status":False,"message":d.get("message","Failed")}),400
    except Exception as e:
        return jsonify({"status":False,"message":str(e)}),500
