"""
Standalone Mongo connection test - isolates auth issues from the Flask app.
Run: python test_mongo_connection.py
"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv not installed - run: pip install python-dotenv")

from pymongo import MongoClient
from pymongo.errors import OperationFailure, ConfigurationError

uri = os.environ.get("MONGO_URI")

if not uri:
    print("MONGO_URI is not set. Check that .env exists in this folder and has a MONGO_URI= line.")
else:
    # Don't print the raw password - just confirm what pymongo will actually try to auth with.
    safe_display = uri.split("@")[-1] if "@" in uri else uri
    print(f"MONGO_URI is set. Connecting to: ...@{safe_display}")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
        print("SUCCESS: authenticated and connected.")
    except OperationFailure as e:
        print(f"AUTH FAILED: {e}")
        print("-> Check username/password in Atlas Database Access, and that any")
        print("   special characters in the password are URL-encoded in MONGO_URI.")
    except ConfigurationError as e:
        print(f"CONFIG ERROR: {e}")
    except Exception as e:
        print(f"CONNECTION FAILED: {type(e).__name__}: {e}")
        print("-> If this is a timeout, check Atlas Network Access allows your current IP.")
