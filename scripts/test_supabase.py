"""
Diagnose Supabase connection issues without exposing secrets.

Run: python scripts/test_supabase.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

url = os.getenv("SUPABASE_URL", "")
key = os.getenv("SUPABASE_SERVICE_KEY", "")

print("=" * 60)
print("SUPABASE CONNECTION DIAGNOSTIC")
print("=" * 60)

# 1. Check env vars are set
if not url:
    print("❌ SUPABASE_URL is empty or missing in .env")
    sys.exit(1)
if not key:
    print("❌ SUPABASE_SERVICE_KEY is empty or missing in .env")
    sys.exit(1)

# 2. Check URL format (without revealing the value)
print(f"\nSUPABASE_URL checks:")
print(f"  starts with https://     : {url.startswith('https://')}")
print(f"  ends with .supabase.co   : {url.endswith('.supabase.co')}")
print(f"  has trailing slash       : {url.endswith('/')}  (should be False)")
print(f"  contains '/rest' or path : {'/rest' in url or url.count('/') > 2}  (should be False)")
print(f"  total length             : {len(url)} chars  (typical: ~40)")

# 3. Check key looks like a JWT
print(f"\nSUPABASE_SERVICE_KEY checks:")
print(f"  starts with 'eyJ'        : {key.startswith('eyJ')}  (JWT format)")
print(f"  total length             : {len(key)} chars  (typical: ~200+)")

# 4. Try raw HTTP to see exactly what's happening
print(f"\nMaking raw HTTP request to {url}/rest/v1/...")
import urllib.request
import urllib.error
import json

req = urllib.request.Request(
    f"{url}/rest/v1/",
    headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
    },
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        print(f"  HTTP {resp.status}")
        print(f"  Body (first 500 chars): {body[:500]}")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code} {e.reason}")
    print(f"  Body: {e.read().decode()[:500]}")
except Exception as e:
    print(f"  Network error: {e}")

# 5. Try listing the symbols table
print(f"\nQuerying symbols table directly...")
req = urllib.request.Request(
    f"{url}/rest/v1/symbols?select=symbol&limit=1",
    headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
    },
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        print(f"  HTTP {resp.status}")
        print(f"  Body: {body[:500]}")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code} {e.reason}")
    print(f"  Body: {e.read().decode()[:500]}")
    if e.code == 404:
        print("\n  → Table 'symbols' doesn't exist. Run the SQL from README step 2.")
except Exception as e:
    print(f"  Network error: {e}")

print("\nDone.")
