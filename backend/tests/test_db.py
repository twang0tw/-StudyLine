import os
import pytest
import certifi
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

load_dotenv()

def verify_mongo_connection(uri: str) -> bool:
    try:
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=2000,
            tlsCAFile=certifi.where()
        )
        client.admin.command('ping')
        return True
    except ConnectionFailure as e:
        print(f"Connection failed: {e}")
        return False

def test_mongodb_connection_success():
    # It is best practice to pull this from your .env during testing
    test_uri = os.getenv("MONGO_TEST_URI")
    if not test_uri:
        pytest.fail("MONGO_TEST_URI environment variable is not set")

    assert verify_mongo_connection(test_uri) is True
