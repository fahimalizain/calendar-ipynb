import logging
from datetime import datetime

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

    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=from_datetime.isoformat() + "Z",
            timeMax=to_datetime.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
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


def get_event_duration(event):
    start_datetime = datetime.fromisoformat(event["start"]["dateTime"])
    end_datetime = datetime.fromisoformat(event["end"]["dateTime"])
    return (end_datetime - start_datetime).total_seconds() // 60


def fetch_calendars(email: str):
    service = get_calendar_service(email)
    calendars_result = service.calendarList().list().execute()
    calendars = calendars_result.get("items", [])
    return calendars
