import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 设置项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

APP_NAME = "idcops"
# 设置工作目录
chdir = str(BASE_DIR)

# 绑定的ip与端口
PORT = os.environ.get("GUNICORN_PORT", 8000)
bind = f"0.0.0.0:{PORT}"

# 进程数
GUNICORN_WORKERS = os.environ.get("GUNICORN_WORKERS", 1)
workers = int(GUNICORN_WORKERS)

# Number of threads per worker process
threads = 3

# Timeout (in seconds) for a request to complete
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))

# The maximum number of requests a worker can handle before being respawned
max_requests = 5000
max_requests_jitter = 500


# 设置访问日志和错误信息日志路径
LOGPATH = BASE_DIR.joinpath("logs")
if not LOGPATH.exists() or not LOGPATH.is_dir():
    LOGPATH.mkdir(exist_ok=True)

accesslog = str(LOGPATH.joinpath("access.log"))
errorlog = str(LOGPATH.joinpath("error.log"))

RUNPATH = BASE_DIR.joinpath("run")
if not RUNPATH.exists() or not RUNPATH.is_dir():
    RUNPATH.mkdir(exist_ok=True)
pidfile = str(RUNPATH.joinpath(f"{APP_NAME}.pid"))

# 设置日志记录水平
loglevel = "info"

# 设置守护进程
daemon = False

# 指定 WSGI 应用
wsgi_app = "idcops.wsgi:application"
