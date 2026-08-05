#!/usr/bin/env python3

import threading
from flask import Flask
from flask_socketio import SocketIO
from core.config_manager import load_config_from_file
from routes.api import api_bp
from services.adsb_service import adsb_worker
from services.serial_service import gps_serial_worker

app = Flask(__name__)
app.config['SECRET_KEY'] = 'liquid_glass_tactical_key'
app.register_blueprint(api_bp)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

if __name__ == '__main__':
    load_config_from_file()
    
    t_adsb = threading.Thread(target=adsb_worker, args=(socketio,), daemon=True)
    t_adsb.start()
    
    t_gps = threading.Thread(target=gps_serial_worker, daemon=True)
    t_gps.start()

    print("=========================================================")
    print(" 📡 ADS-B LoRa Tactical Server attivo su http://127.0.0.1:5000")
    print("=========================================================")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)