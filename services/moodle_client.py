import requests
from config import MOODLE_BASE_URL, MOODLE_TOKEN

class MoodleClient:
    def __init__(self):
        self.endpoint = f"{MOODLE_BASE_URL}/webservice/rest/server.php"

    def call(self, wsfunction: str, params: dict = None):
        if params is None:
            params = {}

        payload = {
            "wstoken": MOODLE_TOKEN,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
            **params
        }

        response = requests.post(self.endpoint, data=payload, timeout=30)
        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict) and "exception" in data:
            raise Exception(f"Moodle API Error: {data}")

        return data
