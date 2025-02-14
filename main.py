from flask import Flask, send_file, redirect, url_for, jsonify
import requests
import threading
import time

app = Flask(__name__)

@app.route('/')
def maintenance():
    return send_file('server.html')

@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for('maintenance'))

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "alive"})

def keep_alive():
    url = "https://nekofilx.onrender.com"
    while True:
        time.sleep(300)  # Sleep for 5 minutes
        try:
            requests.get(url)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
