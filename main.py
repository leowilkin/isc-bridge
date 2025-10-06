import os
import time
import json
from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Tuple
from random import uniform

import requests
from icalevents.icalevents import events as ical_fetch_events
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Environment
ICS_URL = os.environ.get("ICS_URL")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
LOOKAHEAD_DAYS = int(os.environ.get("SYNC_LOOKAHEAD_DAYS", "30"))
LOOKBACK_DAYS = int(os.environ.get("SYNC_LOOKBACK_DAYS", "1"))
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "900"))
SUMMARY_PREFIX = os.environ.get("SUMMARY_PREFIX", "[School]").strip()
BUSY_BLOCKERS = os.environ.get("BUSY_BLOCKERS", "false").lower() == "true"

DATA_DIR = os.path.abspath("./data")
CREDS_DIR = os.path.abspath("./credentials")
TOKEN_PATH = os.path.join(DATA_DIR, "token.json")
STATE_PATH = os.path.join(DATA_DIR, "state.json")
CREDENTIALS_PATH = os.path.join(CREDS_DIR, "credentials.json")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

assert ICS_URL, "ICS_URL is required"

def now_utc():
    return datetime.now(timezone.utc)

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {"last_run": None}

def save_state(state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)

def run_device_flow() -> Credentials:
    with open(CREDENTIALS_PATH, "r") as f:
        config_data = json.load(f)
    config = config_data.get("installed") or config_data.get("web")
    if not config:
        raise ValueError("credentials.json must contain 'installed' or 'web' client config")
    
    client_id = config["client_id"]
    client_secret = config.get("client_secret", "")
    
    payload = {"client_id": client_id, "scope": " ".join(SCOPES)}
    resp = requests.post("https://oauth2.googleapis.com/device/code", data=payload, timeout=30)
    resp.raise_for_status()
    device_data = resp.json()
    
    print(f"[auth] Visit: {device_data.get('verification_url', 'https://www.google.com/device')}")
    print(f"[auth] Enter code: {device_data['user_code']}")
    
    token_payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "device_code": device_data["device_code"],
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }
    
    interval = device_data.get("interval", 5)
    while True:
        time.sleep(interval)
        token_resp = requests.post("https://oauth2.googleapis.com/token", data=token_payload, timeout=30)
        if token_resp.status_code == 200:
            token_data = token_resp.json()
            creds = Credentials(
                token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_uri=config.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )
            return creds
        error = token_resp.json().get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise RuntimeError(f"Device auth failed: {error}")


def get_gcal_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds:
            try:
                creds = run_device_flow()
            except Exception as exc:
                raise RuntimeError(f"Failed to complete OAuth flow: {exc}")
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def event_key(uid: str, start: datetime | date, all_day: bool) -> str:
    # Stable key per occurrence. All-day events key off their local date to avoid TZ drift.
    if all_day:
        fragment = start.date().isoformat() if isinstance(start, datetime) else start.isoformat()
    else:
        fragment = iso(start if isinstance(start, datetime) else datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc))
    return f"{uid}|{fragment}"

def normalize_event_times(ics_ev) -> Tuple[datetime, datetime, bool]:
    """Return timezone-aware start/end along with all-day flag."""
    if ics_ev.start is None or ics_ev.end is None:
        raise ValueError("ICS event missing start or end")

    all_day = bool(getattr(ics_ev, "all_day", False))

    start = ics_ev.start
    end = ics_ev.end

    if isinstance(start, date) and not isinstance(start, datetime):
        start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        all_day = True
    elif isinstance(start, datetime):
        start_dt = start
    else:
        raise TypeError("Unsupported start type")

    if isinstance(end, date) and not isinstance(end, datetime):
        # Google expects the exclusive end date for all-day blocks
        end_dt = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc)
        all_day = True
    elif isinstance(end, datetime):
        end_dt = end
    else:
        raise TypeError("Unsupported end type")

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    tzinfo = start_dt.tzinfo or timezone.utc
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=tzinfo)

    return start_dt, end_dt, all_day

def fetch_ics_window(start: datetime, end: datetime):
    return ical_fetch_events(url=ICS_URL, start=start.date(), end=end.date())

def list_existing_mirrors(service, time_min: str, time_max: str) -> List[Dict]:
    items = []
    page_token = None
    while True:
        try:
            resp = service.events().list(
                calendarId=GOOGLE_CALENDAR_ID,
                privateExtendedProperty=["ics_bridge=true"],
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                singleEvents=True,
                pageToken=page_token,
                showDeleted=False,
                orderBy="startTime",
            ).execute()
            items.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
            time.sleep(uniform(0.1, 0.3))
        except HttpError as e:
            if e.resp.status == 429:
                retry_after = int(e.resp.get('retry-after', 60))
                print(f"[warn] Rate limited, waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            raise
    return items

def gcal_event_from_ics(ics_ev, key: str, start_dt: datetime, end_dt: datetime, all_day: bool) -> Dict:
    # Title handling
    summary = ics_ev.summary or "School event"
    if BUSY_BLOCKERS:
        display_summary = ""
    else:
        display_summary = f"{SUMMARY_PREFIX} {summary}".strip() if SUMMARY_PREFIX else summary

    if all_day:
        start_field = {"date": start_dt.date().isoformat()}
        end_field = {"date": end_dt.date().isoformat()}
    else:
        start_field = {"dateTime": iso(start_dt)}
        end_field = {"dateTime": iso(end_dt)}

    # Determine transparency from ICS event
    # Check TRANSP property: TRANSPARENT = Free, OPAQUE = Busy
    # Also check for busy status indicators
    ics_transp = getattr(ics_ev, "transparent", None)
    show_as = getattr(ics_ev, "show_as", None)
    
    # Default to opaque (busy) unless explicitly set to free/transparent
    if ics_transp is True or (isinstance(ics_transp, str) and ics_transp.upper() == "TRANSPARENT"):
        transparency = "transparent"
    elif show_as and isinstance(show_as, str) and show_as.upper() in ["FREE"]:
        transparency = "transparent"
    else:
        transparency = "opaque"

    body = {
        "summary": display_summary,
        "location": getattr(ics_ev, "location", None),
        "description": getattr(ics_ev, "description", None),
        "start": start_field,
        "end": end_field,
        "visibility": "private",
        "transparency": transparency,
        "extendedProperties": {
            "private": {
                "ics_bridge": "true",
                "ics_key": key,
                "ics_uid": getattr(ics_ev, "uid", ""),
            }
        },
        "source": {
            "title": "School ICS",
            "url": ICS_URL
        },
    }
    return body

def compare_relevant(a: Dict, b: Dict) -> bool:
    fields = ["summary", "location", "description", "visibility", "transparency"]
    times = ["start", "end"]
    for f in fields:
        if (a.get(f) or "") != (b.get(f) or ""):
            return False
    for t in times:
        a_time = a.get(t, {})
        b_time = b.get(t, {})
        a_value = a_time.get("dateTime") or a_time.get("date") or ""
        b_value = b_time.get("dateTime") or b_time.get("date") or ""
        if a_value != b_value:
            return False
    return True

def sync_once():
    service = get_gcal_service()

    window_start = now_utc() - timedelta(days=LOOKBACK_DAYS)
    window_end = now_utc() + timedelta(days=LOOKAHEAD_DAYS)
    time_min = iso(window_start)
    time_max = iso(window_end)

    print(f"[sync] window {time_min} to {time_max}")

    # Fetch ICS events
    ics_events = fetch_ics_window(window_start, window_end)
    wanted: Dict[str, Dict] = {}
    for ev in ics_events:
        status = (getattr(ev, "status", "") or "").upper()
        if status in {"CANCELLED", "CANCELED"}:
            continue
        uid = getattr(ev, "uid", None) or getattr(ev, "id", None) or ""
        try:
            start_dt, end_dt, all_day = normalize_event_times(ev)
        except Exception as exc:
            print(f"[warn] skipping event without usable times ({uid}): {exc}")
            continue
        key = event_key(uid, start_dt.date() if all_day else start_dt, all_day)
        wanted[key] = gcal_event_from_ics(ev, key, start_dt, end_dt, all_day)

    # Fetch existing mirrored Google events
    existing = list_existing_mirrors(service, time_min, time_max)
    existing_by_key = {}
    for ge in existing:
        k = ge.get("extendedProperties", {}).get("private", {}).get("ics_key")
        if k:
            existing_by_key[k] = ge

    # Upsert
    created, updated = 0, 0
    for k, body in wanted.items():
        if k in existing_by_key:
            ge = existing_by_key[k]
            # Build a comparable projection of the existing event
            projection = {
                "summary": ge.get("summary"),
                "location": ge.get("location"),
                "description": ge.get("description"),
                "visibility": ge.get("visibility"),
                "transparency": ge.get("transparency"),
                "start": {
                    "dateTime": ge.get("start", {}).get("dateTime"),
                    "date": ge.get("start", {}).get("date"),
                },
                "end": {
                    "dateTime": ge.get("end", {}).get("dateTime"),
                    "date": ge.get("end", {}).get("date"),
                },
            }
            if not compare_relevant(body, projection):
                try:
                    service.events().patch(
                        calendarId=GOOGLE_CALENDAR_ID,
                        eventId=ge["id"],
                        body=body,
                    ).execute()
                    updated += 1
                    time.sleep(uniform(0.05, 0.15))
                except HttpError as e:
                    if e.resp.status == 429:
                        retry_after = int(e.resp.get('retry-after', 60))
                        print(f"[warn] Rate limited, waiting {retry_after}s")
                        time.sleep(retry_after)
                    else:
                        print(f"[warn] update failed for {k}: {e}")
        else:
            try:
                service.events().insert(
                    calendarId=GOOGLE_CALENDAR_ID,
                    body=body
                ).execute()
                created += 1
                time.sleep(uniform(0.05, 0.15))
            except HttpError as e:
                if e.resp.status == 429:
                    retry_after = int(e.resp.get('retry-after', 60))
                    print(f"[warn] Rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                else:
                    print(f"[warn] create failed for {k}: {e}")

    # Deletions
    deleted = 0
    current_keys = set(wanted.keys())
    for k, ge in existing_by_key.items():
        if k not in current_keys:
            try:
                service.events().delete(
                    calendarId=GOOGLE_CALENDAR_ID,
                    eventId=ge["id"]
                ).execute()
                deleted += 1
                time.sleep(uniform(0.05, 0.15))
            except HttpError as e:
                if e.resp.status == 429:
                    retry_after = int(e.resp.get('retry-after', 60))
                    print(f"[warn] Rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                else:
                    print(f"[warn] delete failed for {k}: {e}")

    print(f"[sync] created={created} updated={updated} deleted={deleted} in_window={len(wanted)}")
    return created, updated, deleted

if __name__ == "__main__":
    while True:
        try:
            sync_once()
        except Exception as e:
            print(f"[error] {e}")
        time.sleep(POLL_SECONDS)
