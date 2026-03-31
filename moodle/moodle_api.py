from services.moodle_client import MoodleClient
import pandas as pd
from tqdm import tqdm
import numpy as np

client = MoodleClient()

def get_all_users():
    result = client.call(
        "core_user_get_users",
        {
            "criteria[0][key]": "email",
            "criteria[0][value]": "%"
        }
    )
    return result.get("users", [])

def get_user_courses(user_id: int):
    """
    Returns courses user is enrolled in,
    with last access time per course
    """
    return client.call(
        "core_enrol_get_users_courses",
        {
            "userid": user_id
        }
    )
