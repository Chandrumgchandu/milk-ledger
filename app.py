import os
import sys
import importlib
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

backend_app_package = importlib.import_module("backend.app")
sys.modules["app"] = backend_app_package
create_app = backend_app_package.create_app


app = create_app()
backend_app_package.app = app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
