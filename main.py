# server.py
from flask import Flask, send_file, redirect, url_for

app = Flask(__name__)

@app.route('/')
def maintenance():
    return send_file('server.html')

@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for('maintenance'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
