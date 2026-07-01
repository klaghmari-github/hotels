from flask import Flask, send_from_directory
from app.config.settings import WEB_DIR
from app.routes.enrich import enrich_bp
from app.routes.simulate import simulate_bp

app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path='/static')
app.register_blueprint(enrich_bp)
app.register_blueprint(simulate_bp)

@app.get('/')
def index():
    return send_from_directory(WEB_DIR, 'index.html')

@app.get('/health')
def health():
    return {'status': 'ok'}

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
