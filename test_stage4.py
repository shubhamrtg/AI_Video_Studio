import requests
import time

BASE_URL = "http://localhost:8001/api/projects"
print("Generating new storyboard project...")

res = requests.post(BASE_URL, json={
    "master_prompt": "A close up of a coffee cup",
    "target_duration": 5
})
project_id = res.json()["id"]

print("Polling storyboard...")
while True:
    project = requests.get(f"{BASE_URL}/{project_id}").json()
    if project["status"] == "STORYBOARD_READY":
        break
    time.sleep(2)

first_shot_id = project["shots"][0]["id"]
print(f"Triggering generation for shot {first_shot_id}...")
requests.post(f"{BASE_URL}/{project_id}/shots/{first_shot_id}/generate")

print("Waiting for generation...")
while True:
    project = requests.get(f"{BASE_URL}/{project_id}").json()
    shot = project["shots"][0]
    print(f"Status: {shot['status']}")
    if shot["status"] == "COMPLETED":
        print(f"Video URL: {shot['video_url']}")
        break
    elif shot["status"] == "FAILED":
        print("Generation failed!")
        break
    time.sleep(5)
