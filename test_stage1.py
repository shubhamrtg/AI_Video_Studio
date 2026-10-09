import requests
import time
import sys

BASE_URL = "http://localhost:8001/api"

print("1. Submitting job...")
response = requests.post(f"{BASE_URL}/jobs", json={"prompt": "A close up of a coffee cup", "duration": 3})
if response.status_code != 200:
    print(f"Error submitting job: {response.text}")
    sys.exit(1)

job_id = response.json()["job_id"]
print(f"Job created: {job_id}")

print("2. Polling job status...")
while True:
    res = requests.get(f"{BASE_URL}/jobs/{job_id}")
    data = res.json()
    status = data["status"]
    print(f"Status: {status}")
    if status == "COMPLETED":
        print(f"Video URL: {data['video_url']}")
        break
    elif status in ["FAILED", "CANCELLED"]:
        print(f"Error: {data.get('error')}")
        break
    time.sleep(5)
