#!/usr/bin/env python3
"""
Google OAuth Token Generator for Vigil v5.0

Run this locally to generate the token, then copy the base64 output to Railway.

Usage:
1. Download OAuth credentials from Google Cloud Console
2. Save as 'credentials.json' in this directory
3. Run: python generate_token.py
4. Complete OAuth in browser
5. Copy the GOOGLE_TOKEN_JSON output to Railway
"""

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
    print("🔐 Vigil v5.0 — Google OAuth Token Generator")
    print("=" * 50)
    
    creds = None
    
    # Check for credentials file
    if not os.path.exists('credentials.json'):
        print("\n❌ ERROR: credentials.json not found!")
        print("\nSteps to fix:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create OAuth 2.0 Client ID (Desktop app)")
        print("3. Download JSON and save as 'credentials.json' here")
        return
    
    # Check for existing token
    if os.path.exists('token.json'):
        print("\n📁 Found existing token.json, checking validity...")
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # Refresh or generate new
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Token expired, refreshing...")
            creds.refresh(Request())
        else:
            print("\n🌐 Opening browser for Google sign-in...")
            print("   Sign in and grant permissions.\n")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save token
        with open('token.json', 'w') as f:
            f.write(creds.to_json())
        print("✅ Token saved to token.json")
    else:
        print("✅ Existing token is valid")
    
    # Output base64 for Railway env var
    with open('token.json', 'r') as f:
        token_data = f.read()
    
    encoded = base64.b64encode(token_data.encode()).decode()
    
    print("\n" + "=" * 60)
    print("📋 GOOGLE_TOKEN_JSON (copy this to Railway):")
    print("=" * 60)
    print(encoded)
    print("=" * 60)
    
    print("\n✅ SUCCESS!")
    print("\nNext steps:")
    print("1. Go to Railway dashboard")
    print("2. Open Vigil service → Variables")
    print("3. Add: GOOGLE_TOKEN_JSON = <paste above value>")
    print("4. Railway will auto-redeploy")
    
    # Test the credentials
    print("\n📊 Testing credentials...")
    try:
        from googleapiclient.discovery import build
        
        # Test Calendar
        calendar = build('calendar', 'v3', credentials=creds)
        calendars = calendar.calendarList().list(maxResults=1).execute()
        print(f"   ✅ Calendar API: OK ({len(calendars.get('items', []))} calendars found)")
        
        # Test Gmail
        gmail = build('gmail', 'v1', credentials=creds)
        profile = gmail.users().getProfile(userId='me').execute()
        print(f"   ✅ Gmail API: OK ({profile.get('emailAddress')})")
        
    except Exception as e:
        print(f"   ⚠️ Test failed: {e}")
        print("   (This might still work - check Railway logs)")

if __name__ == '__main__':
    main()
