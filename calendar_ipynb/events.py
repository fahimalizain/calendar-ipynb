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

    # Filter out All Day Events
    events = [x for x in events if "date" not in x.get("start", {})]

    for event in events:
        event["calendar_id"] = calendar_id
        event["email"] = email
        event["duration_min"] = get_event_duration(event)

    """
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
    events = [x for x in events if x.get("eventType", None) in ("default", "fromGmail")]

    return events


def filter_out_future_events(events: List[dict]):
    """
    - Filters out events which has start date in the FUTURE
    - For events that has started and is still running, we will update it's duration to
      the current time
    """

    # Outright remove events that have started in the future
    now_datetime = datetime.now(pytz.UTC)
    events = [
        x
        for x in events
        if datetime.fromisoformat(x["start"]["dateTime"]) < now_datetime
    ]

    # Update events that have started and are still running
    for event in events:
        end_datetime = datetime.fromisoformat(event["end"]["dateTime"])
        if end_datetime <= now_datetime:
            continue

        start_datetime = datetime.fromisoformat(event["start"]["dateTime"])
        event["duration_min"] = (now_datetime - start_datetime).total_seconds() // 60

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
