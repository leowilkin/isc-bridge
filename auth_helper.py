#!/usr/bin/env python3
"""
Run this locally (not in Docker) to generate data/token.json
Then docker compose up will use the existing token
"""
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_PATH = "./credentials/credentials.json"
TOKEN_PATH = "./data/token.json"

flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
creds = flow.run_local_server(port=0)

os.makedirs("./data", exist_ok=True)
with open(TOKEN_PATH, "w") as token:
    token.write(creds.to_json())

print(f"✓ Token saved to {TOKEN_PATH}")
print("You can now run: docker compose up")
