from typing import List
import re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo


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

    return SleepEventsHandler(events).insert_sleep_events()


class SleepEventsHandler:

    def __init__(self, events: List[dict]):
        from .meta import get_sleep_preferences, get_daily_sleep_minutes

        self.events = events
        self.daily_data = dict()
        self.sleep_preferences = get_sleep_preferences()
        self.daily_sleep_min = get_daily_sleep_minutes()

        if not self.sleep_preferences.get(
            "start_marker"
        ) or not self.sleep_preferences.get("end_marker"):
            raise ValueError("Start and End markers are required for sleep events")

        self.populate_daily_data()

    def insert_sleep_events(self):
        from .events import sort_events

        sleep_events = []
        days = self.get_sleep_days()
        for i in range(len(days) - 1):
            day0 = days[i]
            day1 = days[i + 1]

            d0_end = self.daily_data[day0].get("sleep_marker", None)
            d1_start = self.daily_data[day1].get("wakeup_marker", None)

            if d0_end and d1_start:
                sleep_events.extend(
                    self.create_sleep_event_with_markers(d0_end, d1_start)
                )
            elif d0_end:
                # Only D0 EndMarker Available
                sleep_events.extend(
                    self.create_sleep_event_with_only_end_marker(day0, day1, d0_end)
                )
            elif d1_start:
                # Only D1 StartMarker Available
                sleep_events.extend(
                    self.create_sleep_event_with_only_start_marker(day0, day1, d1_start)
                )
            else:
                # Both D0 EndMarker & D1 StartMarker Not Available
                sleep_events.extend(self.create_sleep_event_with_no_markers(day0, day1))

        sleep_events.extend(self.get_first_day_sleep_event())
        sleep_events.extend(self.get_last_day_sleep_event())

        return sort_events(self.events + sleep_events)

    def get_first_day_sleep_event(self):
        """
        - For the Sleep timings on the first day on events list
            - Use the wakeup marker if available. (Midnight to wakeup marker)
            - Else, use the first event on the day (Midnight to first event)
        """  # noqa: E501
        first_day = self.get_sleep_days()[0]
        first_day_data = self.daily_data[first_day]

        midnight = first_day_data["first_event"].replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        sleep_start = first_day_data["prev_day_sleep_marker"] or midnight
        sleep_end = first_day_data["first_event"]

        if first_day_data.get("wakeup_marker"):
            sleep_end = first_day_data["wakeup_marker"]

        return self.create_base_sleep_events(sleep_start, sleep_end)

    def get_last_day_sleep_event(self):
        """
        - For the Sleep timings on the last day on events list IFF last day is not today
            - Use the sleep marker if available. (Sleep Marker to Midnight)
            - Else, use the last event on the day (Sleep Marker to last event)
        """  # noqa: E501
        last_day = self.get_sleep_days()[-1]
        if last_day == date.today().isoformat():
            return []

        last_day_data = self.daily_data[last_day]
        if last_day_data.get("sleep_marker"):
            # Use sleep marker if available
            next_midnight = (last_day_data["sleep_marker"] + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return self.create_base_sleep_events(
                last_day_data["sleep_marker"], next_midnight
            )

        midnight = last_day_data["first_event"].replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        # It's possible that the last_event ended on next day.
        # In that case, we don't want to create a sleep event
        if last_day_data.get("last_event") and last_day_data["last_event"] < midnight:
            sleep_start = last_day_data["last_event"]
            return self.create_base_sleep_events(sleep_start, midnight)

        return []

    def populate_daily_data(self):
        start_marker = self.sleep_preferences.get("start_marker")
        end_marker = self.sleep_preferences.get("end_marker")

        for event in self.events:
            day = datetime.fromisoformat(event["start"]["dateTime"]).date().isoformat()
            data = self.daily_data.setdefault(
                day,
                dict(
                    prev_day_sleep_marker=None,
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
            end_time = datetime.fromisoformat(event["end"]["dateTime"]).astimezone(
                event_tz
            )
            data["time_zones"][event_tz] = data["time_zones"].get(event_tz, 0) + 1

            # Check for Sleep Start & End Markers
            if re.match(end_marker, summary):
                data["wakeup_marker"] = start_time
            elif re.match(start_marker, summary):
                # Handle the case of post midnight sleeping.
                # We check if the end time is before 7am
                if start_time.hour < 10:
                    # This belongs to the previous day
                    data["prev_day_sleep_marker"] = end_time
                    prev_day = (start_time.date() - timedelta(days=1)).isoformat()
                    if self.daily_data.get(prev_day):
                        self.daily_data[prev_day]["sleep_marker"] = end_time
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

        for d in self.get_sleep_days():
            data = self.daily_data[d]
            data["primary_tz"] = max(data["time_zones"], key=data["time_zones"].get)

    def get_sleep_days(self):
        return sorted(list(set(self.daily_data.keys())))

    def create_base_sleep_events(self, start: datetime, end: datetime):
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

    def create_sleep_event_with_markers(self, start: datetime, end: datetime):
        """
        Both D0 EndMarker & D1 StartMarker Available
        """
        return self.create_base_sleep_events(start, end)

    def create_sleep_event_with_only_end_marker(self, _: str, day1: str, end: datetime):
        """
        Only D0 EndMarker Available
        """
        d1_first_event = self.daily_data[day1].get("first_event", None)
        sleep_end = min(
            end + timedelta(minutes=self.daily_sleep_min), d1_first_event or end
        )
        return self.create_base_sleep_events(end, sleep_end)

    def create_sleep_event_with_only_start_marker(
        self, day0: str, day1: str, start: datetime
    ):
        """
        Only D1 StartMarker Available
        """
        d0_last_event = self.daily_data[day0].get("last_event", None)
        sleep_start = max(
            start - timedelta(minutes=self.daily_sleep_min), d0_last_event or start
        )
        return self.create_base_sleep_events(sleep_start, start)

    def create_sleep_event_with_no_markers(self, day0: str, day1: str):
        """
        Both D0 EndMarker & D1 StartMarker Not Available
        """
        d0_last_event = self.daily_data[day0].get("last_event", None)
        d1_first_event = self.daily_data[day1].get("first_event", None)

        # Sleep start either at D0 LastEvent or 9PM whichever is later
        sleep_start = max(
            d0_last_event,
            datetime.fromisoformat(f"{day0}T21:00:00+00:00").replace(
                tzinfo=d0_last_event.tzinfo
            ),
        )
        sleep_end = min(
            sleep_start + timedelta(minutes=self.daily_sleep_min),
            d1_first_event,
        )

        return self.create_base_sleep_events(sleep_start, sleep_end)
