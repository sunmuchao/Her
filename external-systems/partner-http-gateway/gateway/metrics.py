"""Prometheus metrics 导出模块 - Gateway 性能指标"""

from __future__ import annotations

import logging
import os
import time
from prometheus_client import Counter, Histogram, Gauge, make_wsgi_app
from wsgiref.simple_server import make_server

LOGGER = logging.getLogger(__name__)

# 定义核心指标
REQUEST_COUNT = Counter(
    'gateway_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status', 'surface']
)

REQUEST_LATENCY = Histogram(
    'gateway_request_latency_seconds',
    'HTTP request latency',
    ['method', 'endpoint', 'surface'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

ACTIVE_CONNECTIONS = Gauge(
    'gateway_active_connections',
    'Active HTTP connections',
    ['surface']
)

DATABASE_LATENCY = Histogram(
    'gateway_database_latency_seconds',
    'Database query latency',
    ['database', 'operation'],
    buckets=(0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0)
)

CACHE_HITS = Counter(
    'gateway_cache_hits_total',
    'Cache hit count',
    ['cache_type', 'result']  # result: hit, miss
)

RATE_LIMIT_REJECTIONS = Counter(
    'gateway_rate_limit_rejections_total',
    'Rate limit rejection count',
    ['client_ip', 'endpoint']
)


def setup_metrics_app():
    """创建 metrics WSGI app"""
    return make_wsgi_app()


def metrics_middleware(environ, start_response, app):
    """记录请求指标的中间件

    Args:
        environ: WSGI environ
        start_response: WSGI start_response
        app: 原始 WSGI app

    Returns:
        WSGI response
    """
    start_time = time.time()
    method = environ.get('REQUEST_METHOD', 'GET')
    path = environ.get('PATH_INFO', '/')
    surface = os.environ.get('PARTNER_GATEWAY_SURFACE', 'unknown')

    # 调用原始 app
    response = app(environ, start_response)

    # 记录延迟和请求计数
    latency = time.time() - start_time

    # 从 response 中提取 status code（可能需要适配不同的 WSGI 实现）
    # 这里简化处理，假设 start_response 已被调用
    # 实际实现需要更复杂的逻辑来捕获 status code

    REQUEST_LATENCY.labels(method=method, endpoint=path, surface=surface).observe(latency)
    REQUEST_COUNT.labels(method=method, endpoint=path, status='200', surface=surface).inc()

    return response


def record_database_latency(database_name: str, operation: str, latency_seconds: float):
    """记录数据库查询延迟

    Args:
        database_name: 数据库名称（recommendation, matchmaking, chat等）
        operation: 操作类型（query, insert, update等）
        latency_seconds: 延迟时间（秒）
    """
    DATABASE_LATENCY.labels(database=database_name, operation=operation).observe(latency_seconds)


def record_cache_hit(cache_type: str, result: str):
    """记录缓存命中/未命中

    Args:
        cache_type: 缓存类型（redis, local等）
        result: 结果（hit, miss）
    """
    CACHE_HITS.labels(cache_type=cache_type, result=result).inc()


def record_rate_limit_rejection(client_ip: str, endpoint: str):
    """记录限流拒绝

    Args:
        client_ip: 客户端IP
        endpoint: 请求端点
    """
    RATE_LIMIT_REJECTIONS.labels(client_ip=client_ip, endpoint=endpoint).inc()


def start_metrics_server(port: int = 9091):
    """启动独立的 metrics HTTP 服务

    Args:
        port: metrics 服务端口
    """
    metrics_app = setup_metrics_app()
    httpd = make_server('127.0.0.1', port, metrics_app)
    LOGGER.info(f"Prometheus metrics server started on http://127.0.0.1:{port}/metrics")
    httpd.serve_forever()