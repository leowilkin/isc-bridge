# Agent Instructions for ICS Bridge

## Commands
- Run: `python main.py` (or `docker compose up`)
- Build: `docker compose build`
- Deploy: `docker compose up -d`
- Logs: `docker compose logs -f`
- Admin Panel: http://localhost:8080 (when running)
- Test: No automated tests; verify by checking Google Calendar sync after running
- Lint/Format: No configured linters (use standard Python formatting if editing)

## Architecture
- Single-file Python app (`main.py`) that syncs ICS calendar to Google Calendar
- Runs continuously in a loop (every 15 minutes by default)
- OAuth2 device flow for Google Calendar API authentication
- Persistent storage: `data/token.json` (OAuth token), `data/state.json` (sync state)
- Configuration via environment variables in `.env`

## Code Style
- Python 3.12, type hints preferred (`typing.Dict`, `datetime | date`)
- Google API client libraries: `google-api-python-client`, `google-auth`
- ICS parsing: `icalevents` library
- Use `timezone.utc` for all datetime operations; normalize to UTC via `iso()` helper
- Error handling: catch `HttpError` for API failures, print warnings but continue sync
- Naming: snake_case for functions/variables, UPPER_CASE for module-level constants
