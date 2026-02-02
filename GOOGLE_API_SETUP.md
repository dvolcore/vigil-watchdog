# Google API Setup for Vigil v5.0

## Step 1: Create Google Cloud Project

1. Go to https://console.cloud.google.com/
2. Create new project: "DVOL Vigil" (or use existing)
3. Note your Project ID

## Step 2: Enable APIs

In the Google Cloud Console, enable these APIs:
- Google Calendar API
- Gmail API

Go to: APIs & Services → Library → Search and Enable each

## Step 3: Configure OAuth Consent Screen

1. Go to: APIs & Services → OAuth consent screen
2. Select "External" (or Internal if using Workspace)
3. Fill in:
   - App name: "DVOL Vigil"
   - User support email: your email
   - Developer contact: your email
4. Add scopes:
   - `https://www.googleapis.com/auth/calendar.readonly`
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/gmail.modify`
5. Add your email as a test user
6. Save

## Step 4: Create OAuth Credentials

1. Go to: APIs & Services → Credentials
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: "Desktop app"
4. Name: "Vigil Desktop"
5. Download the JSON file

## Step 5: Generate Token (Run Locally First)

Save this as `generate_token.py` and run on your Mac:

```python
import os
import json
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
]

def main():
    creds = None
    
    # Check for existing token
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # Refresh or generate new
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This will open browser for auth
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save token
        with open('token.json', 'w') as f:
            f.write(creds.to_json())
    
    # Output base64 for Railway env var
    with open('token.json', 'r') as f:
        token_data = f.read()
    
    encoded = base64.b64encode(token_data.encode()).decode()
    print("\n" + "="*50)
    print("GOOGLE_TOKEN_JSON (for Railway):")
    print("="*50)
    print(encoded)
    print("="*50)
    
    print("\n✅ Token generated successfully!")
    print("Add GOOGLE_TOKEN_JSON to Railway environment variables")

if __name__ == '__main__':
    main()
```

## Step 6: Run Token Generator

```bash
# Install dependencies
pip install google-auth-oauthlib google-api-python-client

# Place your downloaded credentials.json in same directory
# Run:
python generate_token.py
```

This will:
1. Open browser for Google sign-in
2. Generate token.json
3. Output base64-encoded token for Railway

## Step 7: Add to Railway

In Railway dashboard, add environment variable:

```
GOOGLE_TOKEN_JSON=<paste the base64 string from step 6>
```

## Step 8: Redeploy Vigil

Railway will auto-redeploy with the new env var.

## Troubleshooting

### "Access blocked" error
- Make sure you added your email as a test user in OAuth consent screen

### Token expired
- Re-run generate_token.py locally
- Update GOOGLE_TOKEN_JSON in Railway

### Refresh token missing
- Delete token.json and re-run generate_token.py
- Make sure "offline" access is requested (it is by default)

## Security Notes

- Keep credentials.json and token.json private
- The base64 token contains refresh capability - treat as secret
- Tokens are stored encrypted in Railway env vars
