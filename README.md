# ICS -> Google Calendar Bridge (self-hosted)

Pulls an Outlook iCal feed and mirrors events into your Google Calendar so your status shows as Busy.

- Read-only input: ICS URL
- Output: creates or updates events in your chosen Google Calendar
- Interval: every 15 minutes by default
- Scope: sync window from now - 1 day to now + 30 days
- Privacy: events set to visibility=private and status Busy

## Quick start

1. Clone these files onto a server with Docker and docker-compose.
2. Create a Google Cloud project and enable the Google Calendar API.
   - OAuth consent screen: External or Internal, add yourself as a test user if External.
   - Create OAuth credentials: Desktop app.
   - Download the client JSON and save it to `credentials/credentials.json`.
3. Copy `.env.example` to `.env` and edit:
   - `ICS_URL` - your Outlook ICS link
   - `GOOGLE_CALENDAR_ID` - usually `primary` or a specific calendar id like you@example.com
   - `ADMIN_PASSWORD` - password for the admin panel (default: `admin`)
   - `SECRET_KEY` - random secret for session encryption (generate with `openssl rand -hex 32`)
4. Build and run:

   ```bash
   docker compose build
   docker compose up
   ```

   On first run, the app prints a Device Authorization URL and code. Open the URL, paste the code, log in to the Google account that owns the target calendar, and grant access. A refresh token will be saved to `data/token.json`.
5. Detach:

   ```bash
   docker compose up -d
   ```

6. Access the admin panel at `http://localhost:8080` to:
   - Manually trigger syncs
   - View sync history with errors and statistics
   - Monitor events added/updated/removed per sync

## Notes

- Deletions: if an event disappears from the ICS within the sync window, the mirrored Google event is deleted.
- Recurring events: expanded within the window. Each occurrence is mapped separately.
- Identification: events carry private extendedProperties with keys `ics_bridge=true` and a stable `ics_key`.
- Conflict strategy: if you edit a mirrored event in Google, the next sync will overwrite it from the ICS source.
- Visibility: `visibility=private`, `transparency=opaque` (Busy). Set `BUSY_BLOCKERS=true` to hide titles.
- You can change `POLL_SECONDS`, `SYNC_LOOKAHEAD_DAYS`, `SYNC_LOOKBACK_DAYS` in `.env`.

## Updating

Pull latest, rebuild, and restart:

```bash
docker compose build
docker compose up -d
```
