import requests
import json

payload = {
  "household_name": "Khan Family",
  "household_city": "Mumbai",
  "members": [
    {
      "id": "abc123",
      "name": "Imran",
      "role": "owner",
      "age_group": "adult",
      "care_needs": []
    },
    {
      "id": "def456",
      "name": "Zara",
      "role": "child",
      "age_group": "child",
      "care_needs": ["screen_time", "homework_reminders"]
    }
  ],
  "devices": [
    {
      "id": "dev111",
      "name": "Living Room TV",
      "device_type": "tv",
      "room": "Living Room"
    }
  ],
  "routines": [
    {
      "id": "school_run",
      "label": "School drop-off",
      "time": "08:00"
    }
  ],
  "priorities": ["security", "family_health"]
}

print("1. Testing /onboarding/complete")
res = requests.post("http://localhost:8000/onboarding/complete", json=payload)
print(res.status_code)
data = res.json()
print(json.dumps(data, indent=2))

if res.status_code == 200:
    hh_id = data["household_id"]
    print(f"\n2. Testing /metrics for household_id={hh_id}")
    res_m = requests.get(f"http://localhost:8000/metrics?household_id={hh_id}")
    print(res_m.status_code)
    print(json.dumps(res_m.json(), indent=2))
    
    print(f"\n3. Testing /graph/{hh_id}")
    res_g = requests.get(f"http://localhost:8000/graph/{hh_id}/full")
    print(res_g.status_code)
    # Output only keys or first few bytes to avoid huge logs
    print(list(res_g.json().keys()))
