import os
import pytz
import json
import logging
from copy import deepcopy
from datetime import datetime, date

from .utils import get_temp_path
from .events import get_calendar_service

logger = logging.getLogger(__name__)


class CalendarDataCache:
    calendarId: str
    email: str
    sync_token: str
    events: list
    last_sync: datetime


def sync_events(email: str, calendarId: str) -> CalendarDataCache:
    data = _get_data_cache(email, calendarId)
    service = get_calendar_service(email)

    sync_token = data.sync_token
    page_token = None
    all_events = [*data.events]

    deleted = 0
    updated = 0
    added = 0

    try:
        while True:
            # Prepare request parameters
            request_params = {
                "calendarId": calendarId,
                "pageToken": page_token,
                "maxResults": 500,
                "singleEvents": True,
                "showDeleted": True,
            }

            # Add syncToken if we have one from previous sync
            if sync_token:
                request_params["syncToken"] = sync_token

            events_result = service.events().list(**request_params).execute()
            events = events_result.get("items", [])
            logger.debug(
                f"Fetched {len(events)} events from calendar {email}/{calendarId}"
            )

            for event in events:
                if event.get("status") == "cancelled":
                    # Remove cancelled events from our cache
                    prev_len = len(all_events)
                    all_events = [e for e in all_events if e["id"] != event["id"]]
                    if len(all_events) < prev_len:
                        deleted += 1
                else:
                    # Update or add new events
                    existing_idx = next(
                        (i for i, e in enumerate(all_events) if e["id"] == event["id"]),
                        None,
                    )
                    if existing_idx is not None:
                        updated += 1
                        all_events[existing_idx] = event
                    else:
                        added += 1
                        all_events.append(event)

            # Get the next page token
            page_token = events_result.get("nextPageToken")
            if not page_token:
                # No more pages, save the new sync token
                sync_token = events_result.get("nextSyncToken")
                break

    except Exception as e:
        if "Sync token is no longer valid" in str(
            e
        ) or "Invalid sync token value" in str(e):
            logger.warning(
                f"Sync token is no longer valid for {email}/{calendarId}. "
                "Performing full sync."
            )
            # Handle expired sync token by performing a full sync
            _delete_data_cache(email, calendarId)
            return sync_events(email, calendarId)
        raise e

    data.sync_token = sync_token
    data.events = all_events
    data.last_sync = datetime.now(tz=pytz.UTC)
    _update_data_cache(data)

    logger.info(
        f"Sync completed for {email}/{calendarId}: "
        f"Added {added}, Updated {updated}, Deleted {deleted}"
    )

    return data


def _get_data_cache(email: str, calendarId: str) -> CalendarDataCache:
    try:
        with open(_get_data_cache_path(email, calendarId), "r") as f:
            data = json.load(f)
            cache = CalendarDataCache()
            cache.sync_token = data.get("sync_token", "")
            cache.events = data.get("events", [])
            cache.calendarId = data.get("calendarId", calendarId)
            cache.email = data.get("email", email)
            cache.last_sync = datetime.fromisoformat(
                data.get("last_sync", datetime.now().isoformat())
            )
            return cache
    except (FileNotFoundError, json.JSONDecodeError):
        # Return empty cache if file doesn't exist or is invalid
        cache = CalendarDataCache()
        cache.sync_token = ""
        cache.events = []
        cache.calendarId = calendarId
        cache.email = email
        cache.last_sync = datetime.now()
        return cache


def _update_data_cache(data: CalendarDataCache):
    cache_data = {
        "sync_token": data.sync_token,
        "events": data.events,
        "calendarId": data.calendarId,
        "email": data.email,
        "last_sync": data.last_sync.isoformat(),
    }
    with open(_get_data_cache_path(data.email, data.calendarId), "w") as f:
        json.dump(cache_data, f, indent=2)


def _delete_data_cache(email: str, calendarId: str):
    try:
        os.remove(_get_data_cache_path(email, calendarId))
    except FileNotFoundError:
        pass


def _get_data_cache_path(email: str, calendarId: str) -> str:
    os.makedirs(get_temp_path("all_events"), exist_ok=True)

    return get_temp_path(f"all_events/{email}_{calendarId}.json")


def fetch_events(
    email: str, calendar_id: str, from_datetime: datetime, to_datetime: datetime
):
    data = sync_events(email, calendar_id)
    events = data.events

    filtered_events = []
    for event in events:
        if "start" in event and "dateTime" in event["start"]:
            start_time = datetime.fromisoformat(event["start"]["dateTime"])
            if from_datetime <= start_time <= to_datetime:
                filtered_events.append(event)
        elif "start" in event and "date" in event["start"]:
            # Handle all-day events
            start_date = date.fromisoformat(event["start"]["date"])
            end_date = date.fromisoformat(event["end"]["date"])

            if from_datetime.date() <= start_date <= to_datetime.date():
                filtered_events.append(event)

            if from_datetime.date() <= end_date <= to_datetime.date():
                filtered_events.append(event)

    filtered_events = deepcopy(filtered_events)
    for event in filtered_events:
        event["calendar_id"] = calendar_id
        event["email"] = email

    return filtered_events
