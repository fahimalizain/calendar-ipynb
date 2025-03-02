import logging
import re
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

    logger.info(f"Fetching events from {from_datetime} to {to_datetime} for {email}")
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


def insert_sleep_events(events: List[dict]):
    """
    Insert a Sleep Event for all the days we have events.
    - Every night, we make two sleep events. 1st on D0 till Midnight, 2nd from D1 Midnight till Daybreak
    - Logic for Calculating Sleep Duration based on Marker Availability:
        - D0 EndMarker & D1 StartMarker Available
            - We calculate Sleep from D0 EndMarker to D1 StartMarker
        - D0 EndMarker Available & D1 StartMarker Not Available
            - We calculate Sleep from D0 EndMarker to Earliest(End+DailySleepHours, 1st Event on D1)
        - D0 EndMarker Not Available & D1 StartMarker Available
            - We calculate Sleep ending at D1 StartMarker and starting at Latest(D0 LastEvent, D1 StartMarker-DailySleepHours)
        - D0 EndMarker Not Available & D1 StartMarker Not Available
            - We calculate Sleep with DailySleepHours, starting at D0 LastEvent and ending at D1 FirstEvent
    - For the Sleep timings on the first day on events list
        - Use the wakeup marker if available. (Midnight to wakeup marker)
        - Else, use the first event on the day (Midnight to first event) (sleep_duration_min will be considered)
    - For the Sleep timings on the last day on events list IFF last day is not today
        - Use the sleep marker if available. (Sleep Marker to Midnight)
        - Else, use the last event on the day (Sleep Marker to last event) (sleep_duration_min // 3)

    TODO: For first and last day, incorporate the sleep_duration_min to logic to prevent inflated numbers
    """  # noqa: E501
    from .meta import get_sleep_preferences, get_daily_sleep_minutes

    sleep_preferences = get_sleep_preferences()
    daily_sleep_min = get_daily_sleep_minutes()

    start_marker = sleep_preferences.get("start_marker")
    end_marker = sleep_preferences.get("end_marker")
    if not start_marker or not end_marker:
        return events

    # Days with events
    daily_data = dict()
    for event in events:
        day = datetime.fromisoformat(event["start"]["dateTime"]).date().isoformat()
        data = daily_data.setdefault(
            day,
            dict(
                wakeup_marker=None,
                sleep_marker=None,
                first_event=None,
                last_event=None,
                primary_tz=None,
                time_zones=dict(),
            ),
        )

        summary = event.get("summary", "").strip()
        event_tz = ZoneInfo(event["start"]["timeZone"])
        start_time = datetime.fromisoformat(event["start"]["dateTime"]).astimezone(
            event_tz
        )
        end_time = datetime.fromisoformat(event["end"]["dateTime"]).astimezone(event_tz)
        data["time_zones"][event_tz] = data["time_zones"].get(event_tz, 0) + 1

        # Check for Sleep Start & End Markers
        if re.match(end_marker, summary):
            data["wakeup_marker"] = start_time
        elif re.match(start_marker, summary):
            # Handle the case of post midnight sleeping.
            # We check if the end time is before 6am
            if start_time.hour < 6:
                # This belongs to the previous day
                prev_day = (start_time.date() - timedelta(days=1)).isoformat()
                if daily_data.get(prev_day):
                    daily_data[prev_day]["sleep_marker"] = end_time
            else:
                data["sleep_marker"] = end_time

        # Check for First & Last Events
        if data["first_event"] is None:
            data["first_event"] = start_time
        elif start_time < data["first_event"]:
            data["first_event"] = start_time

        if data["last_event"] is None:
            data["last_event"] = end_time
        elif end_time > data["last_event"]:
            data["last_event"] = end_time

    days = sorted(list(set(daily_data.keys())))
    for d in days:
        data = daily_data[d]
        data["primary_tz"] = max(data["time_zones"], key=data["time_zones"].get)

    def create_base_sleep_events(start: datetime, end: datetime):
        """
        This function will split the sleep event into two events.
        - 1st event will be from start till midnight
        - 2nd event will be from midnight till end
        - If both start and end are on the same day, we don't split
        """

        def create_event(start: datetime, end: datetime) -> dict:
            return {
                "summary": "Sleeping",
                "start": {
                    "dateTime": start.isoformat(),
                    "timeZone": start.tzinfo.key,
                },
                "end": {
                    "dateTime": end.isoformat(),
                    "timeZone": end.tzinfo.key,
                },
                "duration_min": (end - start).total_seconds() // 60,
                "visibility": "default",
                "status": "confirmed",
            }

        if start.tzinfo != end.tzinfo:
            raise ValueError("Start and End times must be in the same timezone")

        if start.date() == end.date():
            return [create_event(start, end)]
        else:
            midnight = (start + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=start.tzinfo
            )
            return [
                x
                for x in [create_event(start, midnight), create_event(midnight, end)]
                if x["duration_min"] > 0
            ]

    def create_sleep_event_with_markers(start: datetime, end: datetime):
        """
        Both D0 EndMarker & D1 StartMarker Available
        """
        return create_base_sleep_events(start, end)

    def create_sleep_event_with_only_end_marker(_: str, day1: str, end: datetime):
        """
        Only D0 EndMarker Available
        """
        d1_first_event = daily_data[day1].get("first_event", None)
        sleep_end = min(end + timedelta(minutes=daily_sleep_min), d1_first_event or end)
        return create_base_sleep_events(end, sleep_end)

    def create_sleep_event_with_only_start_marker(
        day0: str, day1: str, start: datetime
    ):
        """
        Only D1 StartMarker Available
        """
        d0_last_event = daily_data[day0].get("last_event", None)
        sleep_start = max(
            start - timedelta(minutes=daily_sleep_min), d0_last_event or start
        )
        return create_base_sleep_events(sleep_start, start)

    def create_sleep_event_with_no_markers(day0: str, day1: str):
        """
        Both D0 EndMarker & D1 StartMarker Not Available
        """
        d0_last_event = daily_data[day0].get("last_event", None)
        d1_first_event = daily_data[day1].get("first_event", None)

        # Sleep start either at D0 LastEvent or 9PM whichever is later
        sleep_start = max(
            d0_last_event,
            datetime.fromisoformat(f"{day0}T21:00:00+00:00").replace(
                tzinfo=d0_last_event.tzinfo
            ),
        )
        sleep_end = min(
            sleep_start + timedelta(minutes=daily_sleep_min),
            d1_first_event,
        )

        return create_base_sleep_events(sleep_start, sleep_end)

    sleep_events = []
    for i in range(len(days) - 1):
        day0 = days[i]
        day1 = days[i + 1]

        d0_end = daily_data[day0].get("sleep_marker", None)
        d1_start = daily_data[day1].get("wakeup_marker", None)

        if d0_end and d1_start:
            sleep_events.extend(create_sleep_event_with_markers(d0_end, d1_start))
        elif d0_end:
            # Only D0 EndMarker Available
            sleep_events.extend(
                create_sleep_event_with_only_end_marker(day0, day1, d0_end)
            )
        elif d1_start:
            # Only D1 StartMarker Available
            sleep_events.extend(
                create_sleep_event_with_only_start_marker(day0, day1, d1_start)
            )
        else:
            # Both D0 EndMarker & D1 StartMarker Not Available
            sleep_events.extend(create_sleep_event_with_no_markers(day0, day1))

    # Handle first Day
    """
    - For the Sleep timings on the first day on events list
        - Use the wakeup marker if available. (Midnight to wakeup marker)
        - Else, use the first event on the day (Midnight to first event)
    """  # noqa: E501
    first_day = days[0]
    first_day_data = daily_data[first_day]
    if first_day_data.get("wakeup_marker"):
        # Use wakeup marker if available
        midnight = first_day_data["wakeup_marker"].replace(hour=0, minute=0, second=0)
        sleep_events.extend(
            create_base_sleep_events(midnight, first_day_data["wakeup_marker"])
        )
    elif first_day_data.get("first_event"):
        # Use first event if no wakeup marker
        midnight = first_day_data["first_event"].replace(hour=0, minute=0, second=0)
        sleep_events.extend(
            create_base_sleep_events(midnight, first_day_data["first_event"])
        )

    # Handle last Day
    """
    - For the Sleep timings on the last day on events list IFF last day is not today
        - Use the sleep marker if available. (Sleep Marker to Midnight)
        - Else, use the last event on the day (Sleep Marker to last event)
    """  # noqa: E501
    last_day = days[-1]
    if last_day != date.today().isoformat():
        last_day_data = daily_data[last_day]
        if last_day_data.get("sleep_marker"):
            # Use sleep marker if available
            next_midnight = (last_day_data["sleep_marker"] + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sleep_events.extend(
                create_base_sleep_events(last_day_data["sleep_marker"], next_midnight)
            )
        elif last_day_data.get("last_event"):
            # Use last event plus 1/3 of daily sleep duration
            next_midnight = (last_day_data["last_event"] + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sleep_start = last_day_data["last_event"]
            sleep_events.extend(create_base_sleep_events(sleep_start, next_midnight))

    return sort_events(events + sleep_events)


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
