import requests
import time
import sys

BASE_URL = "http://localhost:8001/api/projects"

prompt = "Create a cinematic 15-second video showing a professional craftsman assembling a miniature Porsche 911 GT3 RS. Only the craftsman's hands and forearms are visible."

print("1. Creating Project & Generating Storyboard...")
res = requests.post(BASE_URL, json={
    "master_prompt": prompt,
    "target_duration": 15
})

if res.status_code != 200:
    print(f"Error: {res.text}")
    sys.exit(1)

project = res.json()
project_id = project["id"]
print(f"Project ID: {project_id}")

print("2. Polling for Storyboard completion...")
while True:
    res = requests.get(f"{BASE_URL}/{project_id}")
    project = res.json()
    if project["status"] == "STORYBOARD_READY":
        print("\n=== STORYBOARD GENERATED ===")
        for shot in project["shots"]:
            print(f"Shot {shot['shot_number']} ({shot['duration']}s): {shot['description']}")
        break
    elif project["status"] == "FAILED":
        print("Storyboard generation failed.")
        sys.exit(1)
    time.sleep(2)

print("\n3. Triggering Shot 1 Video Generation...")
first_shot = project["shots"][0]
res = requests.post(f"{BASE_URL}/{project_id}/shots/{first_shot['id']}/generate")
print(f"Generate response: {res.status_code} - {res.text}")
