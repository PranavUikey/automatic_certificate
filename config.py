import os
from dotenv import load_dotenv

load_dotenv()

MOODLE_BASE_URL = os.getenv("MOODLE_BASE_URL")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN")

if not MOODLE_BASE_URL or not MOODLE_TOKEN:
    raise RuntimeError("MOODLE_BASE_URL or MOODLE_TOKEN missing in .env")
