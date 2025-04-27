from urllib.parse import quote_plus

import requests

key = "27181d3f8ddc4ff5ac1258c1c0d2eee7"  # or your new key
address = "10, Đông Hưng Thuận 10, District 12, Ho Chi Minh City, 71507, Vietnam"
encoded_address = quote_plus(address)
url = f"https://api.geoapify.com/v1/geocode/search?text={encoded_address}&apiKey={key}&lang=vi&limit=1&format=json"
headers = {"Accept": "application/json", "User-Agent": "TestClient/1.0"}
response = requests.get(url, headers=headers)
print("Status code:", response.status_code)
print("Response:", response.json())
