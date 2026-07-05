"""
Run this ONCE locally to get your Gmail OAuth2 refresh token.
Usage:
  1. Download your OAuth client JSON from Google Cloud Console
  2. Run: python get_gmail_token.py path/to/client_secret.json
  3. A browser window will open — log in as contact@wondershopexperiences.com
  4. Copy the three values printed at the end into your Railway variables
"""
import sys
import json

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Installing required package...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "google-auth-oauthlib", "--break-system-packages"], check=True)
    from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def main():
    if len(sys.argv) < 2:
        print("Usage: python get_gmail_token.py path/to/client_secret.json")
        sys.exit(1)

    client_secrets_file = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(client_secrets_file) as f:
        client_info = json.load(f)["installed"]

    print("\n" + "="*60)
    print("✅ Add these 3 variables to Railway:")
    print("="*60)
    print(f"GMAIL_CLIENT_ID     = {client_info['client_id']}")
    print(f"GMAIL_CLIENT_SECRET = {client_info['client_secret']}")
    print(f"GMAIL_REFRESH_TOKEN = {creds.refresh_token}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
