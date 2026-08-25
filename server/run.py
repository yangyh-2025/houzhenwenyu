"""启动入口：python run.py"""
import uvicorn

from app.core.config import get_settings
from app.main import create_app

s = get_settings()
app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=s.host, port=s.port, log_config=None)
