import os
import json
import threading
from datetime import datetime, timezone
from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
from functools import wraps
from main import sync_once

DATA_DIR = os.path.abspath("./data")
HISTORY_PATH = os.path.join(DATA_DIR, "sync_history.json")
BLOCKED_RANGES_PATH = os.path.join(DATA_DIR, "blocked_ranges.json")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())
sync_lock = threading.Lock()

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    return []

def save_history(history):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history[-100:], f, indent=2)

def load_blocked_ranges():
    if os.path.exists(BLOCKED_RANGES_PATH):
        with open(BLOCKED_RANGES_PATH, "r") as f:
            return json.load(f)
    return []

def save_blocked_ranges(ranges):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(BLOCKED_RANGES_PATH, "w") as f:
        json.dump(ranges, f, indent=2)

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

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>ICS Bridge Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }
        .login-box {
            background: #1e293b;
            padding: 40px;
            border-radius: 12px;
            border: 1px solid #334155;
            width: 100%;
            max-width: 400px;
        }
        h1 {
            color: #f1f5f9;
            margin-bottom: 30px;
            font-size: 24px;
            text-align: center;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #cbd5e1;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px;
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 6px;
            color: #e2e8f0;
            font-size: 16px;
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #3b82f6;
        }
        button {
            width: 100%;
            background: #3b82f6;
            color: white;
            border: none;
            padding: 12px;
            font-size: 16px;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover { background: #2563eb; }
        .error {
            background: #7f1d1d;
            color: #fca5a5;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid #991b1b;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>🔐 ICS Bridge Login</h1>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autofocus>
            </div>
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
"""

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
        
        <div style="display: flex; gap: 10px; margin-bottom: 30px;">
            <button class="sync-button" onclick="runSync()" id="syncBtn" style="flex: 1; margin: 0;">
                Manual Sync Now
            </button>
            <button class="sync-button" onclick="logout()" style="background: #64748b; flex: 0 0 auto; margin: 0;">
                Logout
            </button>
        </div>
        
        <div class="status" id="status"></div>
        
        <h2 style="margin-bottom: 16px;">Blocked Date Ranges</h2>
        <p style="color: #94a3b8; margin-bottom: 16px; font-size: 14px;">Events within these date ranges will not be synced from the ICS feed.</p>
        <div style="display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap;">
            <input type="date" id="blockStart" style="padding: 10px; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0;">
            <span style="color: #64748b; align-self: center;">to</span>
            <input type="date" id="blockEnd" style="padding: 10px; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0;">
            <input type="text" id="blockReason" placeholder="Reason (optional)" style="padding: 10px; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; flex: 1; min-width: 150px;">
            <button onclick="addBlockedRange()" style="background: #ef4444; color: white; border: none; padding: 10px 16px; border-radius: 6px; cursor: pointer;">Block Range</button>
        </div>
        <table style="margin-bottom: 30px;">
            <thead>
                <tr>
                    <th>Start Date</th>
                    <th>End Date</th>
                    <th>Reason</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody id="blockedBody">
                <tr><td colspan="4" style="text-align: center;">Loading...</td></tr>
            </tbody>
        </table>
        
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
        function logout() {
            window.location.href = '/logout';
        }
        
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
        
        function updateBlockedRanges() {
            fetch('/api/blocked-ranges')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('blockedBody');
                    if (data.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #64748b;">No blocked ranges</td></tr>';
                        return;
                    }
                    tbody.innerHTML = data.map((range, idx) => `
                        <tr>
                            <td>${range.start}</td>
                            <td>${range.end}</td>
                            <td class="stat">${range.reason || '—'}</td>
                            <td>
                                <button onclick="deleteBlockedRange(${idx})" style="background: #dc2626; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;">Remove</button>
                            </td>
                        </tr>
                    `).join('');
                });
        }
        
        function addBlockedRange() {
            const start = document.getElementById('blockStart').value;
            const end = document.getElementById('blockEnd').value;
            const reason = document.getElementById('blockReason').value;
            
            if (!start || !end) {
                alert('Please select both start and end dates');
                return;
            }
            if (start > end) {
                alert('Start date must be before or equal to end date');
                return;
            }
            
            fetch('/api/blocked-ranges', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({start, end, reason})
            })
            .then(r => r.json())
            .then(() => {
                document.getElementById('blockStart').value = '';
                document.getElementById('blockEnd').value = '';
                document.getElementById('blockReason').value = '';
                updateBlockedRanges();
            });
        }
        
        function deleteBlockedRange(idx) {
            fetch('/api/blocked-ranges/' + idx, {method: 'DELETE'})
                .then(() => updateBlockedRanges());
        }
        
        updateBlockedRanges();
        updateHistory();
        setInterval(updateHistory, 10000);
    </script>
</body>
</html>
"""

@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == ADMIN_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        return render_template_string(LOGIN_TEMPLATE, error="Invalid password")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route("/")
@require_auth
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/history")
@require_auth
def get_history():
    return jsonify(load_history())

@app.route("/api/blocked-ranges")
@require_auth
def get_blocked_ranges():
    return jsonify(load_blocked_ranges())

@app.route("/api/blocked-ranges", methods=["POST"])
@require_auth
def add_blocked_range():
    data = request.get_json()
    start = data.get("start")
    end = data.get("end")
    reason = data.get("reason", "")
    
    if not start or not end:
        return jsonify({"error": "start and end required"}), 400
    
    ranges = load_blocked_ranges()
    ranges.append({"start": start, "end": end, "reason": reason})
    ranges.sort(key=lambda r: r["start"])
    save_blocked_ranges(ranges)
    return jsonify({"success": True})

@app.route("/api/blocked-ranges/<int:idx>", methods=["DELETE"])
@require_auth
def delete_blocked_range(idx):
    ranges = load_blocked_ranges()
    if 0 <= idx < len(ranges):
        ranges.pop(idx)
        save_blocked_ranges(ranges)
    return jsonify({"success": True})

@app.route("/api/sync", methods=["POST"])
@require_auth
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
