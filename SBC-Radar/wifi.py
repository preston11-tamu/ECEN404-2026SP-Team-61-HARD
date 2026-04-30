import os
import requests
import time
import datetime

#PUBLISH_URL = os.environ["ALERT_PUBLISH_URL"]     # full https URL
#HEARTBEAT_URL = os.environ["HEARTBEAT_PUBLISH_URL"]
#API_KEY = os.environ["API_KEY"]            # key

PUBLISH_URL = "https://publishalert-ufrpqieccq-uc.a.run.app"	#fix hard coding later, for testing
HEARTBEAT_URL = "https://deviceheartbeat-ufrpqieccq-uc.a.run.app"
API_KEY = "hard-pi-9f3a2c7b-ALERTS"	#fix hard coding later

def publish_alert(room: str, alert_type: str = "Fall detected", confidence=None):
    payload = {
        "type": alert_type,
        "room": room,
    }
    if confidence is not None:
        payload["confidence"] = int(confidence)

    r = requests.post(
        PUBLISH_URL,
        headers={"x-api-key": API_KEY},
        json=payload,
        timeout=5,
    )
    r.raise_for_status()
    return r.json()  

def heartbeat():
	time = str(datetime.datetime.now())
	payload = {
		"deviceId": "Pi On",
	}
	r = requests.post(
		HEARTBEAT_URL,
		headers={"x-api-key": API_KEY},
		json=payload,
		timeout=5,
	)
	r.raise_for_status()
	return r.json()  
