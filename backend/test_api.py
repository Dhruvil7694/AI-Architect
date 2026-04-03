"""
Test the user API endpoints
"""
import requests
import json

BASE_URL = "http://localhost:8000"

print("Testing User API Endpoints\n")
print("=" * 50)

# Test 1: Login
print("\n1. Testing Login...")
login_data = {
    "email": "admin@example.com",
    "password": "admin123"
}
response = requests.post(f"{BASE_URL}/api/auth/login/", json=login_data)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"Response: {json.dumps(response.json(), indent=2)}")
else:
    print(f"Error: {response.text}")

# Test 2: Get all users
print("\n2. Testing Get Users...")
response = requests.get(f"{BASE_URL}/api/admin/users/")
print(f"Status: {response.status_code}")
if response.status_code == 200:
    users = response.json()
    print(f"Found {len(users)} users")
    for user in users:
        print(f"  - {user['email']} ({user['name']}) - Roles: {user['roles']}")
else:
    print(f"Error: {response.text}")

print("\n" + "=" * 50)
print("Tests completed!")
