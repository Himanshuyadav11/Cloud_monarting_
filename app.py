import time
import threading
import psutil
import platform
from datetime import datetime
from collections import deque
from flask import Flask, jsonify, render_template, Response

# Configuration
SAMPLE_INTERVAL = 1.0    # seconds between samples
HISTORY_LEN = 300        # keep last 300 samples (~5 minutes if interval=1s)
ALERT_CPU_PERCENT = 80
ALERT_MEM_PERCENT = 80
PROMETHEUS_ENABLED = True

app = Flask(__name__)

# In-memory time-series buffers
timestamps = deque(maxlen=HISTORY_LEN)
cpu_history = deque(maxlen=HISTORY_LEN)
mem_history = deque(maxlen=HISTORY_LEN)
disk_history = deque(maxlen=HISTORY_LEN)
net_sent_history = deque(maxlen=HISTORY_LEN)
net_recv_history = deque(maxlen=HISTORY_LEN)

# Initial previous net counters for delta calculation
_prev_net = psutil.net_io_counters()
_start_time = time.time()


def sample_metrics():
    """Background sampler that collects system metrics periodically."""
    global _prev_net
    while True:
        now = datetime.utcnow().isoformat() + "Z"
        timestamps.append(now)

        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent

        net = psutil.net_io_counters()
        # Use totals (not per-second). Frontend can compute delta if wanted.
        net_sent = net.bytes_sent
        net_recv = net.bytes_recv

        cpu_history.append(cpu)
        mem_history.append(mem)
        disk_history.append(disk)
        net_sent_history.append(net_sent)
        net_recv_history.append(net_recv)

        _prev_net = net
        time.sleep(SAMPLE_INTERVAL)


@app.route("/")
def index():
    """Render the dashboard page. The page will request /metrics for live data."""
    system_info = {
        "hostname": platform.node(),
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python_version": platform.python_version(),
        "psutil_version": psutil.__version__,
        "start_time": datetime.utcfromtimestamp(_start_time).isoformat() + "Z",
    }
    return render_template(
        "index.html",
        sample_interval=SAMPLE_INTERVAL,
        alert_cpu=ALERT_CPU_PERCENT,
        alert_mem=ALERT_MEM_PERCENT,
        system_info=system_info,
    )


@app.route("/metrics")
def metrics():
    """Return latest metrics and history as JSON for the frontend to consume."""
    # compute uptime in seconds
    uptime_seconds = int(time.time() - _start_time)
    loadavg = None
    try:
        loadavg = list(psutil.getloadavg())
    except (AttributeError, OSError):
        loadavg = []

    latest = {
        "timestamp": timestamps[-1] if timestamps else datetime.utcnow().isoformat() + "Z",
        "cpu_percent": cpu_history[-1] if cpu_history else psutil.cpu_percent(),
        "mem_percent": mem_history[-1] if mem_history else psutil.virtual_memory().percent,
        "disk_percent": disk_history[-1] if disk_history else psutil.disk_usage("/").percent,
        "net_sent": net_sent_history[-1] if net_sent_history else psutil.net_io_counters().bytes_sent,
        "net_recv": net_recv_history[-1] if net_recv_history else psutil.net_io_counters().bytes_recv,
        "uptime_seconds": uptime_seconds,
        "loadavg": loadavg,
        "process_count": len(psutil.pids()),
    }

    history = {
        "timestamps": list(timestamps),
        "cpu": list(cpu_history),
        "mem": list(mem_history),
        "disk": list(disk_history),
        "net_sent": list(net_sent_history),
        "net_recv": list(net_recv_history),
    }

    return jsonify({"latest": latest, "history": history})


@app.route("/metrics_prometheus")
def metrics_prometheus():
    """Expose a tiny Prometheus-format metrics endpoint (text/plain)."""
    # This is a basic exporter - for production consider prometheus_client library
    latest_cpu = cpu_history[-1] if cpu_history else psutil.cpu_percent()
    latest_mem = mem_history[-1] if mem_history else psutil.virtual_memory().percent
    latest_disk = disk_history[-1] if disk_history else psutil.disk_usage("/").percent
    proc_count = len(psutil.pids())
    uptime_seconds = int(time.time() - _start_time)

    metrics_lines = [
        "# HELP system_cpu_percent CPU usage percent",
        "# TYPE system_cpu_percent gauge",
        f"system_cpu_percent {latest_cpu}",
        "# HELP system_mem_percent Memory usage percent",
        "# TYPE system_mem_percent gauge",
        f"system_mem_percent {latest_mem}",
        "# HELP system_disk_percent Disk usage percent",
        "# TYPE system_disk_percent gauge",
        f"system_disk_percent {latest_disk}",
        "# HELP system_process_count Number of processes",
        "# TYPE system_process_count gauge",
        f"system_process_count {proc_count}",
        "# HELP system_uptime_seconds Uptime in seconds since exporter start",
        "# TYPE system_uptime_seconds counter",
        f"system_uptime_seconds {uptime_seconds}",
    ]
    return Response("\n".join(metrics_lines) + "\n", mimetype="text/plain; charset=utf-8")


if __name__ == "__main__":
    # start sampler thread
    sampler = threading.Thread(target=sample_metrics, daemon=True)
    sampler.start()

    # Pre-sample a few times quickly to populate history for frontend when it loads
    for _ in range(3):
        time.sleep(0.1)

    # In debug mode enable reloader only if you want. For production use gunicorn or similar.
    app.run(host="0.0.0.0", port=5000, debug=True)

