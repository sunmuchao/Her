# Gunicorn 配置文件
# 用于 Partner HTTP Gateway

import multiprocessing

# 服务器配置
bind = "127.0.0.1:8765"
workers = multiprocessing.cpu_count() * 2 + 1  # 推荐：CPU核心数 * 2 + 1
worker_class = "sync"  # 同步 worker，适合数据库密集型应用
threads = 1  # 每个 worker 的线程数（sync worker 不支持多线程）

# 超时配置
timeout = 60  # worker 超时时间（秒），增加到 60秒避免数据库认证中断
graceful_timeout = 15  # 优雅关闭超时时间
keepalive = 5  # HTTP keep-alive 时间

# 进程管理
max_requests = 1000  # 每个 worker 处理的最大请求数，达到后重启（防止内存泄漏）
max_requests_jitter = 50  # 添加随机性，避免所有 worker 同时重启
preload_app = False  # 不预加载应用，避免数据库连接池问题

# 日志配置（使用绝对路径）
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_dir = os.path.join(project_root, ".run", "logs")
os.makedirs(log_dir, exist_ok=True)

accesslog = os.path.join(log_dir, "gunicorn_access.log")
errorlog = os.path.join(log_dir, "gunicorn_error.log")
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程名称
proc_name = "her-gateway"

# 安全配置
limit_request_line = 4094  # HTTP 请求行最大长度
limit_request_fields = 100  # HTTP header 数量限制
limit_request_field_size = 8190  # HTTP header 大小限制

# 其他配置
capture_output = True  # 捕获 stdout/stderr
enable_stdio_inheritance = False  # 不继承 stdio