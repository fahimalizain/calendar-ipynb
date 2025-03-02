import json
import logging
import re

from .utils import get_temp_path

"""
Labelling / Classification is done based on User preference.
For now, we assume that the user's preference is stored at temp/user_preferences.json
"""

logger = logging.getLogger(__name__)


def classify_events(events):
    preferences = load_preferences()
    unclassified_events = []
    for event in events:
        event["categories"] = classify_event(event, preferences.get("categories", {}))
        if event["categories"]:
            logger.debug(
                f"Event {event['summary']} classified as {event['categories']}"
            )
        else:
            logger.debug(f"Event {event['summary']} not classified")
            unclassified_events.append(event)

    if len(unclassified_events) > 0:
        logger.warning(f"\n\nUnclassified events: {len(unclassified_events)}")
        for event in unclassified_events:
            logger.warning(f"Event {event['summary']} not classified")
    else:
        logger.debug("✅ All events classified")

    return events


def load_preferences():
    file_path = get_temp_path("user_preferences.json")
    with open(file_path, "r") as f:
        return json.load(f)


def check_patterns(event, patterns):
    if not patterns:
        return False

    text = event.get("summary", "").strip()
    calendar_id = event.get("calendar_id", "")
    for pattern in patterns:
        if "regex" in pattern and re.match(pattern["regex"], text):
            return True

        if "calendarId" in pattern:
            if isinstance(pattern["calendarId"], list):
                if calendar_id in pattern["calendarId"]:
                    return True
            elif isinstance(pattern["calendarId"], str):
                if pattern["calendarId"] == calendar_id:
                    return True

    return False


def classify_event(event, preferences):
    results = []

    for category, config in preferences.items():
        # Check main category patterns
        if "patterns" in config and check_patterns(event, config["patterns"]):
            results.append((category, config["title"]))

        # Check children categories
        if "children" in config:
            for child_category, child_config in config["children"].items():
                if "patterns" in child_config and check_patterns(
                    event, child_config["patterns"]
                ):
                    results.append(
                        (f"{category}/{child_category}", child_config["title"])
                    )

    if len(set(x[0].split("/")[0] for x in results)) > 1:
        logger.warning(f"Multiple Labels Found on {event['summary']}: {results}")

    return results


def get_sleep_preferences():
    preferences = load_preferences()
    return preferences.get("sleep", {})


def get_daily_sleep_minutes():
    """
    Get the daily sleep hours from the user preferences (default is 8, in minutes)
    """
    preferences = load_preferences()
    hours = preferences.get("sleep", {}).get("daily_sleep_hours", 8)
    in_minutes = round(hours * 60)
    return in_minutes
