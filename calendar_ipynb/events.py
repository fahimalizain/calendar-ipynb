import logging
from typing import List
from datetime import datetime, date, timedelta
import pytz

from googleapiclient.discovery import build

from .google_oauth import get_account_credentials

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_calendar_service(email: str):
    creds = get_account_credentials(email)
    return build("calendar", "v3", credentials=creds)


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

    logger.info(f"Fetching events from {from_datetime} to {to_datetime} for {email}")
    service = get_calendar_service(email)

    events = []
    page_token = None

    while True:
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=from_datetime.isoformat() + "Z",
                timeMax=to_datetime.isoformat() + "Z",
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
    events = [
        x
        for x in events
        if datetime.fromisoformat(x["start"]["dateTime"]) < datetime.now(pytz.UTC)
    ]

    # Update events that have started and are still running
    for event in events:
        end_datetime = datetime.fromisoformat(event["end"]["dateTime"])
        if end_datetime <= datetime.now(pytz.UTC):
            continue

        start_datetime = datetime.fromisoformat(event["start"]["dateTime"])
        event["duration_min"] = (
            datetime.now(pytz.UTC) - start_datetime
        ).total_seconds() // 60

    return events


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
    from .meta import get_daily_sleep_minutes

    sleep_min = get_daily_sleep_minutes()
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
        untracked_duration_min = (24 * 60) - tracked_duration - sleep_min
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
