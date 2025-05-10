import logging
from typing import Dict, List
from datetime import datetime, date, timedelta
import pytz
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from .google_oauth import get_account_credentials

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_calendar_service(email: str):
    creds = get_account_credentials(email)
    return build("calendar", "v3", credentials=creds)


def get_primary_timezone(selected_calendars: Dict[str, List[str]]):

    time_zone_map = dict()
    for email, calendars in selected_calendars.items():
        service = get_calendar_service(email)
        for calendar in calendars:
            cal_result = service.calendars().get(calendarId=calendar).execute()
            time_zone_map[calendar] = cal_result.get("timeZone")

    timezones = list(time_zone_map.values())
    primary = max(set(timezones), key=timezones.count)
    return ZoneInfo(primary)


def fetch_events(
    email: str,
    calendar_id: str,
    from_datetime: datetime,
    to_datetime: datetime,
):
    """
    DEPRECATED: Use fetch_events_incremental instead.
    This is kept in-case we need to fetch events from a specific calendar without
    syncing the entire calendar.
    """
    if not from_datetime or not to_datetime:
        raise ValueError("Please provide from_date and to_date")

    if from_datetime > to_datetime:
        raise ValueError("from_date must be before to_date")

    logger.info(
        f"Fetching events from {from_datetime.isoformat()} to {to_datetime.isoformat()}"
        f"for {email}"
    )
    service = get_calendar_service(email)

    events = []
    page_token = None

    while True:
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=from_datetime.isoformat(),
                timeMax=to_datetime.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )

        events.extend(events_result.get("items", []))

        page_token = events_result.get("nextPageToken", None)
        if not page_token:
            break

    logger.debug(
        f"Found {len(events)} events in the date range {from_datetime} to {to_datetime}"
        " for {email} in {calendar_id}"
    )

    for event in events:
        event["calendar_id"] = calendar_id
        event["email"] = email

    return events


def fetch_events_parallel(
    email_map: Dict[str, List[str]], from_datetime: datetime, to_datetime: datetime
):
    from concurrent.futures import ThreadPoolExecutor
    from functools import partial
    from .events_incremental import fetch_events as fetch_events_incremental

    def fetch_calendar_events(email, calendar, from_datetime, to_datetime):
        """Helper function to fetch events for a single calendar"""
        return fetch_events_incremental(
            email=email,
            calendar_id=calendar,
            from_datetime=from_datetime,
            to_datetime=to_datetime,
        )

    # Replace the sequential fetching with parallel fetching
    fetched_events = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Create a list of tasks to execute
        tasks = []
        for email, calendars in email_map.items():
            for calendar in calendars:
                # Create a partial function with the fixed arguments
                task = partial(
                    fetch_calendar_events, email, calendar, from_datetime, to_datetime
                )
                tasks.append(task)

        # Execute all tasks in parallel and gather results
        results = list(executor.map(lambda x: x(), tasks))

        # Flatten the results
        for result in results:
            fetched_events.extend(result)
    return fetched_events


def filter_out_all_day_events(events: List[dict]):
    """
    Filters out all-day events from the list of events.
    All-day events are identified by the presence of "date" in the start dictionary.
    """
    filtered_events = [
        event for event in events if "date" not in event.get("start", {})
    ]
    logger.debug(f"Filtered out {len(events) - len(filtered_events)} all-day events")
    return filtered_events


def filter_out_event_types(events: List[dict], event_types: List[str]):
    """
    Filters out events based on their event types.
    Event types to be filtered out are provided in the event_types list.
    - Event Types can be found here:
      https://developers.google.com/calendar/api/v3/reference/events

    Specific type of the event. This cannot be modified after the event is created.
    Possible values are:
        "birthday" - A special all-day event with an annual recurrence.
        "default" - A regular event or not further specified.
        "focusTime" - A focus-time event.
        "fromGmail" - An event from Gmail. This type of event cannot be created.
        "outOfOffice" - An out-of-office event.
        "workingLocation" - A working location event.
    """
    filtered_events = [
        event for event in events if event.get("eventType") in event_types
    ]
    logger.debug(
        f"Filtered out {len(events) - len(filtered_events)}, keeping {event_types}"
    )
    return filtered_events


def add_duration_minutes(events: List[dict]):
    """
    Adds duration in minutes to each event in the list.
    The duration is calculated as the difference between the end and start times.
    """
    for event in events:
        event["duration_min"] = get_event_duration(event)

    return events


def filter_out_future_events(events: List[dict], to_datetime: datetime):
    """
    - Filters out events which has start date in the FUTURE
    - For events that has started and is still running, we will update it's duration to
      the current time
    """

    # Outright remove events that have started in the future
    now_datetime = datetime.now(pytz.UTC)
    boundary_datetime = min(to_datetime, now_datetime)

    events = [
        x
        for x in events
        if datetime.fromisoformat(x["start"]["dateTime"]) < boundary_datetime
    ]

    # Update events that have started and are still running
    for event in events:
        end_datetime = datetime.fromisoformat(event["end"]["dateTime"])
        if end_datetime <= boundary_datetime:
            continue

        start_datetime = datetime.fromisoformat(event["start"]["dateTime"])
        event["duration_min"] = (
            boundary_datetime - start_datetime
        ).total_seconds() // 60

    return events


def filter_out_past_events(from_datetime: datetime, events: List[dict]):
    """
    Filters out past events and updates ongoing events:
    - Removes events that have ended before `from_datetime`.
    - Updates the start time of events that started before `from_datetime`.

    Args:
        from_datetime (datetime): The reference datetime.
        events (List[dict]): List of event dictionaries.

    Returns:
        List[dict]: Filtered and updated list of events.
    """
    filtered_events = []

    for event in events:
        try:
            start_datetime = datetime.fromisoformat(event["start"]["dateTime"])
            end_datetime = datetime.fromisoformat(event["end"]["dateTime"])
        except (KeyError, ValueError) as e:
            filtered_events.append(event)
            logger.debug(f"Skipping non dateTime event: {event}. Error: {e}")
            continue

        # Remove events that have ended in the past
        if end_datetime < from_datetime:
            logger.debug(f"Removing past event: {event}")
            continue

        # Update start time of events that have started in the past
        if start_datetime < from_datetime:
            logger.debug(f"Updating ongoing event: {event}")
            event["start"]["dateTime"] = from_datetime.isoformat()
            event["duration_min"] = (end_datetime - from_datetime).total_seconds() // 60

        filtered_events.append(event)

    return filtered_events


def breakdown_overnight_events(events: List[dict]):
    """
    Breaks down overnight events into two separate events:
    - One for the part before midnight
    - One for the part after midnight
    """
    if not events:
        return events

    new_events = []
    for event in events:
        start_datetime = datetime.fromisoformat(event["start"]["dateTime"])
        midnight = (start_datetime + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_datetime = datetime.fromisoformat(event["end"]["dateTime"])

        # We check if the event spans overnight also we check if the end time is after midnight  # noqa: E501
        # to avoid splitting events that end at midnight
        if start_datetime.date() != end_datetime.date() and end_datetime > midnight:
            # Split the event into two parts
            new_events.append(
                {
                    **event,
                    "end": {"dateTime": midnight.isoformat(), "timeZone": "UTC"},
                    "duration_min": (midnight - start_datetime).total_seconds() // 60,
                }
            )
            new_events.append(
                {
                    **event,
                    "start": {"dateTime": midnight.isoformat(), "timeZone": "UTC"},
                    "duration_min": (end_datetime - midnight).total_seconds() // 60,
                }
            )
        else:
            new_events.append(event)

    return new_events


def handle_overlapping_event_durations(events: List[dict]):
    """
    Handles overlapping events using a time-slice approach:
    - Identifies all unique time boundaries
    - For each time slice, splits duration equally among overlapping events
    """
    if not events:
        return events

    # Get all unique time boundaries
    boundaries = set()
    for event in events:
        start = datetime.fromisoformat(event["start"]["dateTime"])
        end = datetime.fromisoformat(event["end"]["dateTime"])
        boundaries.add(start)
        boundaries.add(end)

    boundaries = sorted(list(boundaries))

    # Reset all event durations to 0
    for event in events:
        event["duration_min"] = 0

    # Process each time slice
    for i in range(len(boundaries) - 1):
        slice_start = boundaries[i]
        slice_end = boundaries[i + 1]
        slice_duration = (slice_end - slice_start).total_seconds() / 60

        # Find events active during this slice
        active_events = []
        for event in events:
            event_start = datetime.fromisoformat(event["start"]["dateTime"])
            event_end = datetime.fromisoformat(event["end"]["dateTime"])
            if event_start <= slice_start and event_end >= slice_end:
                active_events.append(event)

        # Split this slice's duration among active events
        if active_events:
            duration_per_event = slice_duration / len(active_events)
            for event in active_events:
                event["duration_min"] += duration_per_event

    return events


def sort_events(events):
    return sorted(
        events,
        key=lambda x: (
            datetime.fromisoformat(x["start"]["dateTime"]),
            -x["duration_min"],
        ),
    )


def insert_untracked_times(events: List[dict]):
    """
    Inserts a New Google Calendar Event with duration set to
    untracked time (excluding sleep time).

    We could improve this function by sprinkling the untracked events
    in the actual gaps between tracked events.
    """
    daily_tracked = dict()
    for event in events:
        if event["duration_min"] <= 0:
            continue

        date_key = datetime.fromisoformat(event["start"]["dateTime"]).date().isoformat()
        if date_key not in daily_tracked:
            daily_tracked[date_key] = 0

        daily_tracked[date_key] += event["duration_min"]

    # Remove today's tracked time
    daily_tracked.pop(date.today().isoformat(), None)

    for date_key, tracked_duration in daily_tracked.items():
        untracked_duration_min = (24 * 60) - tracked_duration
        if untracked_duration_min <= 0:
            continue

        date_obj = date.fromisoformat(date_key)
        start_datetime = datetime(
            year=date_obj.year,
            month=date_obj.month,
            day=date_obj.day,
            hour=0,
            minute=0,
            second=0,
            tzinfo=pytz.UTC,
        )
        end_datetime = start_datetime + timedelta(minutes=untracked_duration_min)

        events.append(
            {
                "summary": f"{untracked_duration_min} min | Untracked",
                "start": {
                    "dateTime": start_datetime.isoformat(),
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": end_datetime.isoformat(),
                    "timeZone": "UTC",
                },
                "visibility": "default",
                "status": "confirmed",
                # Custom
                "duration_min": untracked_duration_min,
            }
        )

    return sort_events(events)


def get_event_duration(event):
    start_datetime = datetime.fromisoformat(event["start"]["dateTime"])
    end_datetime = datetime.fromisoformat(event["end"]["dateTime"])
    return (end_datetime - start_datetime).total_seconds() // 60


def fetch_calendars(email: str):
    service = get_calendar_service(email)
    calendars_result = service.calendarList().list().execute()
    calendars = calendars_result.get("items", [])
    return calendars


def pretty_print_timedelta(td: timedelta) -> str:
    total_seconds = int(td.total_seconds())
    days, remainder = divmod(total_seconds, 86400)  # 86400 seconds in a day
    hours, remainder = divmod(remainder, 3600)  # 3600 seconds in an hour
    minutes, seconds = divmod(remainder, 60)  # 60 seconds in a minute

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:  # Include seconds if no other parts exist
        parts.append(f"{seconds}s")

    return " ".join(parts)


def delete_and_duplicate_recurring_event_instance(
    email: str,
    calendar_id: str,
    instance: dict,
):
    service = get_calendar_service(email)
    logger.info(
        "Deleting and duplicating event instance: %s", instance.get("summary", "")
    )  # noqa: E501
    new_event = {
        "summary": instance.get("summary", ""),
        "description": instance.get("description", ""),
        "location": instance.get("location", ""),
        "start": instance.get("start"),
        "end": instance.get("end"),
        "attendees": instance.get("attendees", []),
        "reminders": instance.get("reminders", {"useDefault": True}),
        "colorId": instance.get("colorId", None),
        "visibility": instance.get("visibility", "default"),
        "status": instance.get("status", "confirmed"),
        "eventType": instance.get("eventType", "default"),
    }

    # Create a new event with the same details as the instance
    created_event = (
        service.events().insert(calendarId=calendar_id, body=new_event).execute()
    )
    logger.info(f"Created new event: {created_event.get('htmlLink')}")

    # Delete the original instance
    instance["status"] = "cancelled"
    service.events().update(
        calendarId=calendar_id, eventId=instance["id"], body=instance
    ).execute()
    logger.info(f"Deleted original instance: {instance.get('htmlLink')}")
    return created_event


def process_events_and_classify(
    events: List[dict],
    from_datetime: datetime,
    to_datetime: datetime,
    event_types: List[str],
):
    # Process Events
    # Make a deep copy of the fetched events to avoid modifying the original list
    from copy import deepcopy
    from .meta import classify_events
    from .sleep_events import insert_sleep_events

    events = deepcopy(events)

    print("Total Events Fetched:", len(events))
    events = filter_out_all_day_events(events)
    events = filter_out_event_types(events, event_types=event_types)
    events = add_duration_minutes(events)
    events = breakdown_overnight_events(events)
    events = filter_out_future_events(events, to_datetime=to_datetime)
    events = filter_out_past_events(from_datetime=from_datetime, events=events)
    events = sort_events(events)
    events = insert_sleep_events(events)
    events = handle_overlapping_event_durations(events)
    events = insert_untracked_times(events)
    events = classify_events(events)

    return events
