"""路径与常量（跨域共享；以 backend/ 为基准）。"""
import os

# backend/common/paths.py -> dirname=backend/common -> dirname=backend
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = BACKEND_DIR
UPLOAD_DIR = os.path.join(BASE_DIR, '..', 'uploads')
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')
DATASOURCE_DIR = os.path.join(BASE_DIR, '..', 'datasource')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATASOURCE_DIR, exist_ok=True)