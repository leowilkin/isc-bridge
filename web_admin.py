import os
import json
import threading
from datetime import datetime, timezone
from flask import Flask, render_template_string, jsonify, request
from main import sync_once

DATA_DIR = os.path.abspath("./data")
HISTORY_PATH = os.path.join(DATA_DIR, "sync_history.json")

app = Flask(__name__)
sync_lock = threading.Lock()

def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    return []

def save_history(history):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history[-100:], f, indent=2)

def add_sync_record(success, created=0, updated=0, deleted=0, error_msg=None):
    history = load_history()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "error": error_msg
    }
    history.append(record)
    save_history(history)
    return record

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>ICS Bridge Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: #f1f5f9;
            margin-bottom: 30px;
            font-size: 28px;
        }
        .sync-button {
            background: #3b82f6;
            color: white;
            border: none;
            padding: 12px 24px;
            font-size: 16px;
            border-radius: 6px;
            cursor: pointer;
            margin-bottom: 30px;
            transition: background 0.2s;
        }
        .sync-button:hover { background: #2563eb; }
        .sync-button:disabled {
            background: #475569;
            cursor: not-allowed;
        }
        .status {
            background: #1e293b;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 30px;
            border: 1px solid #334155;
        }
        .status.syncing { border-color: #3b82f6; }
        .status.error { border-color: #ef4444; }
        .status.success { border-color: #10b981; }
        table {
            width: 100%;
            border-collapse: collapse;
            background: #1e293b;
            border-radius: 8px;
            overflow: hidden;
        }
        th {
            background: #334155;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #f1f5f9;
        }
        td {
            padding: 12px;
            border-top: 1px solid #334155;
        }
        tr:hover { background: #334155; }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge.success { background: #10b981; color: white; }
        .badge.error { background: #ef4444; color: white; }
        .stat { color: #94a3b8; }
        .error-msg { color: #fca5a5; font-size: 14px; }
        .timestamp { color: #64748b; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔄 ICS Bridge Admin</h1>
        
        <button class="sync-button" onclick="runSync()" id="syncBtn">
            Manual Sync Now
        </button>
        
        <div class="status" id="status"></div>
        
        <h2 style="margin-bottom: 16px;">Sync History</h2>
        <table id="historyTable">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Status</th>
                    <th>Added</th>
                    <th>Updated</th>
                    <th>Removed</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody id="historyBody">
                <tr><td colspan="6" style="text-align: center;">Loading...</td></tr>
            </tbody>
        </table>
    </div>
    
    <script>
        function formatDate(isoStr) {
            const d = new Date(isoStr);
            return d.toLocaleString();
        }
        
        function updateHistory() {
            fetch('/api/history')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('historyBody');
                    if (data.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">No sync history yet</td></tr>';
                        return;
                    }
                    tbody.innerHTML = data.reverse().map(record => `
                        <tr>
                            <td class="timestamp">${formatDate(record.timestamp)}</td>
                            <td>
                                <span class="badge ${record.success ? 'success' : 'error'}">
                                    ${record.success ? 'Success' : 'Failed'}
                                </span>
                            </td>
                            <td class="stat">${record.created}</td>
                            <td class="stat">${record.updated}</td>
                            <td class="stat">${record.deleted}</td>
                            <td class="error-msg">${record.error || '—'}</td>
                        </tr>
                    `).join('');
                });
        }
        
        function runSync() {
            const btn = document.getElementById('syncBtn');
            const status = document.getElementById('status');
            
            btn.disabled = true;
            btn.textContent = 'Syncing...';
            status.className = 'status syncing';
            status.textContent = '⏳ Sync in progress...';
            
            fetch('/api/sync', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        status.className = 'status success';
                        status.textContent = `✓ Sync complete! Added: ${data.created}, Updated: ${data.updated}, Removed: ${data.deleted}`;
                    } else {
                        status.className = 'status error';
                        status.textContent = `✗ Sync failed: ${data.error}`;
                    }
                    updateHistory();
                })
                .catch(err => {
                    status.className = 'status error';
                    status.textContent = '✗ Request failed: ' + err.message;
                })
                .finally(() => {
                    btn.disabled = false;
                    btn.textContent = 'Manual Sync Now';
                });
        }
        
        updateHistory();
        setInterval(updateHistory, 10000);
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/history")
def get_history():
    return jsonify(load_history())

@app.route("/api/sync", methods=["POST"])
def trigger_sync():
    if not sync_lock.acquire(blocking=False):
        return jsonify({"success": False, "error": "Sync already in progress"}), 409
    
    try:
        created, updated, deleted = sync_once()
        record = add_sync_record(True, created, updated, deleted)
        return jsonify({
            "success": True,
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "timestamp": record["timestamp"]
        })
    except Exception as e:
        error_msg = str(e)
        add_sync_record(False, error_msg=error_msg)
        return jsonify({"success": False, "error": error_msg}), 500
    finally:
        sync_lock.release()

if __name__ == "__main__":
    port = int(os.environ.get("WEB_PORT", "8080"))
    try:
        from waitress import serve
        print(f"[web] Starting production server on port {port}")
        serve(app, host="0.0.0.0", port=port, threads=4)
    except ImportError:
        print(f"[web] Starting development server on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False)
