import socket
import ssl
from datetime import datetime, timezone as dt_timezone

import requests
from django.conf import settings


class MetricsUnavailable(RuntimeError):
    pass


def _api_query(expression):
    try:
        response = requests.get(
            settings.PROMETHEUS_URL + '/api/v1/query',
            params={'query': expression},
            timeout=(2, 4),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get('status') != 'success':
            raise MetricsUnavailable('Prometheus query did not succeed')
        return payload.get('data', {}).get('result', [])
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise MetricsUnavailable from exc


def query_value(expression):
    rows = _api_query(expression)
    if not rows:
        return None
    try:
        return float(rows[0]['value'][1])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MetricsUnavailable from exc


def query_labels(expression):
    rows = _api_query(expression)
    return rows[0].get('metric', {}) if rows else {}


def service_up(job):
    value = query_value(f'up{{job="{job}"}}')
    return None if value is None else bool(value >= 1)


def certificate_status(hostname):
    if not hostname or hostname in {'localhost', '127.0.0.1'}:
        return {'status': 'not_configured'}
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=3) as raw:
            with context.wrap_socket(raw, server_hostname=hostname) as secured:
                certificate = secured.getpeercert()
        raw_expiry = certificate.get('notAfter')
        if not raw_expiry:
            return {'status': 'unknown'}
        expiry = datetime.strptime(raw_expiry, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=dt_timezone.utc)
        remaining = (expiry - datetime.now(dt_timezone.utc)).total_seconds() / 86400
        return {'status': 'ok' if remaining > 14 else 'warning', 'days_remaining': round(remaining, 1), 'expires_at': expiry.isoformat()}
    except (OSError, ssl.SSLError, ValueError):
        return {'status': 'unavailable'}


def caddy_health():
    try:
        response = requests.get('http://caddy:8081/healthz', timeout=(1, 2))
        return response.status_code == 200
    except requests.RequestException:
        return False


def snapshot():
    metrics = {}
    queries = {
        'cpu_current_percent': '100-(avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))*100)',
        'cpu_percent': '100-(avg(rate(node_cpu_seconds_total{mode="idle"}[10m]))*100)',
        'memory_total': 'node_memory_MemTotal_bytes',
        'memory_available': 'node_memory_MemAvailable_bytes',
        'disk_total': 'node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}',
        'disk_available': 'node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}',
        'inodes_total': 'node_filesystem_files{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}',
        'inodes_free': 'node_filesystem_files_free{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}',
        'uptime_seconds': 'time()-node_boot_time_seconds',
        'load1': 'node_load1',
        'load5': 'node_load5',
        'load15': 'node_load15',
    }
    for key, expression in queries.items():
        try:
            metrics[key] = query_value(expression)
        except MetricsUnavailable:
            metrics[key] = None

    if metrics.get('memory_total') and metrics.get('memory_available') is not None:
        metrics['memory_used'] = metrics['memory_total'] - metrics['memory_available']
        metrics['memory_percent'] = 100 * metrics['memory_used'] / metrics['memory_total']
    else:
        metrics['memory_used'] = None
        metrics['memory_percent'] = None

    if metrics.get('disk_total') and metrics.get('disk_available') is not None:
        metrics['disk_used'] = metrics['disk_total'] - metrics['disk_available']
        metrics['disk_percent'] = 100 * metrics['disk_used'] / metrics['disk_total']
    else:
        metrics['disk_used'] = None
        metrics['disk_percent'] = None

    if metrics.get('inodes_total') and metrics.get('inodes_free') is not None:
        metrics['inode_percent'] = 100 * (1 - metrics['inodes_free'] / metrics['inodes_total'])
    else:
        metrics['inode_percent'] = None

    try:
        uname = query_labels('node_uname_info')
    except MetricsUnavailable:
        uname = {}
    metrics['host'] = {
        'hostname': uname.get('nodename', ''),
        'kernel': uname.get('release', ''),
        'os': uname.get('sysname', ''),
        'machine': uname.get('machine', ''),
    }
    try:
        cadvisor = query_labels('cadvisor_version_info')
    except MetricsUnavailable:
        cadvisor = {}
    metrics['docker_version'] = cadvisor.get('dockerVersion') or cadvisor.get('docker_version') or ''
    return metrics


def prometheus_targets():
    result = {}
    for job in ('node', 'postgres', 'cadvisor', 'django'):
        try:
            result[job] = service_up(job)
        except MetricsUnavailable:
            result[job] = None
    return result


def celery_worker_status(timeout=1.5):
    """Actively check Celery worker reachability, separately from Beat."""
    try:
        from celery import current_app
        replies = current_app.control.inspect(timeout=timeout).ping() or {}
    except Exception:
        return {'ok': False, 'workers': [], 'error': 'unavailable'}
    workers = sorted(str(name)[:200] for name, payload in replies.items() if payload)
    return {'ok': bool(workers), 'workers': workers, 'error': ''}
