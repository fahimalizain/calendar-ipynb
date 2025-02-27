import json
import os
from datetime import datetime, time, timedelta
from typing import Tuple

import ipywidgets as widgets
from IPython.display import DisplayHandle

from calendar_ipynb.utils import get_temp_path

from enum import Enum


class DateRangePreset(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"
    LAST_7_DAYS = "last_7_days"
    LAST_14_DAYS = "last_14_days"
    THIS_MONTH = "this_month"
    LAST_30_DAYS = "last_30_days"
    CUSTOM = "custom"


DATE_RANGE_SELECTION_CACHE = get_temp_path("date_range_selection.json")

_date_selection_widget = None
_display_handle = None


def build_widget():
    global _date_selection_widget

    _from_date, _to_date = get_selection_from_cache()

    from_date_picker = widgets.DatePicker(
        description="From:",
        disabled=False,
        value=_from_date,
    )
    to_date_picker = widgets.DatePicker(
        description="To:",
        disabled=False,
        value=_to_date,
    )

    # Create buttons
    today_btn = widgets.Button(description="Today")
    yesterday_btn = widgets.Button(description="Yesterday")
    this_week_btn = widgets.Button(description="This Week")
    last_7_days_btn = widgets.Button(description="Last 7 Days")
    last_14_days_btn = widgets.Button(description="Last 14 Days")
    this_month_btn = widgets.Button(description="This Month")
    last_30_days_btn = widgets.Button(description="Last 30 Days")

    # Create button handlers
    def set_today(b):
        today = datetime.now().date()
        from_date_picker.value = today
        to_date_picker.value = today
        cache_selection(DateRangePreset.TODAY)

    def set_yesterday(b):
        yesterday = (datetime.now() - timedelta(days=1)).date()
        from_date_picker.value = yesterday
        to_date_picker.value = yesterday
        cache_selection(DateRangePreset.YESTERDAY)

    def set_this_week(b):
        today = datetime.now().date()
        first_day = today - timedelta(days=today.weekday())
        from_date_picker.value = first_day
        to_date_picker.value = today
        cache_selection(DateRangePreset.THIS_WEEK)

    def set_last_7_days(b):
        today = datetime.now().date()
        last_week = (datetime.now() - timedelta(days=7)).date()
        from_date_picker.value = last_week
        to_date_picker.value = today
        cache_selection(DateRangePreset.LAST_7_DAYS)

    def set_last_14_days(b):
        today = datetime.now().date()
        two_weeks_ago = (datetime.now() - timedelta(days=14)).date()
        from_date_picker.value = two_weeks_ago
        to_date_picker.value = today
        cache_selection(DateRangePreset.LAST_14_DAYS)

    def set_this_month(b):
        today = datetime.now().date()
        first_day = today.replace(day=1)
        from_date_picker.value = first_day
        to_date_picker.value = today
        cache_selection(DateRangePreset.THIS_MONTH)

    def set_last_30_days(b):
        today = datetime.now().date()
        thirty_days_ago = (datetime.now() - timedelta(days=30)).date()
        from_date_picker.value = thirty_days_ago
        to_date_picker.value = today
        cache_selection(DateRangePreset.LAST_30_DAYS)

    # Attach handlers to buttons
    today_btn.on_click(set_today)
    yesterday_btn.on_click(set_yesterday)
    this_week_btn.on_click(set_this_week)
    last_7_days_btn.on_click(set_last_7_days)
    last_14_days_btn.on_click(set_last_14_days)
    this_month_btn.on_click(set_this_month)
    last_30_days_btn.on_click(set_last_30_days)

    # Create horizontal button container
    buttons = widgets.HBox(
        [
            today_btn,
            yesterday_btn,
            this_week_btn,
            last_7_days_btn,
            last_14_days_btn,
            this_month_btn,
            last_30_days_btn,
        ]
    )

    # Combine date pickers and buttons
    _date_selection_widget = widgets.VBox(
        [widgets.HBox([from_date_picker, to_date_picker]), buttons]
    )

    def observe_date_change(*args, **kwargs):
        cache_selection(DateRangePreset.CUSTOM)

    from_date_picker.observe(observe_date_change)
    to_date_picker.observe(observe_date_change)


def cache_selection(preset: DateRangePreset = None, *args, **kwargs):
    data = {}

    if preset and preset != DateRangePreset.CUSTOM:
        data["preset"] = preset
    else:
        # from_date, to_date = get_selected_date_range()
        from_date = _date_selection_widget.children[0].children[0].value
        to_date = _date_selection_widget.children[0].children[1].value
        if from_date:
            data["from_date"] = from_date.isoformat()
        if to_date:
            data["to_date"] = to_date.isoformat()
        data["preset"] = DateRangePreset.CUSTOM

    with open(DATE_RANGE_SELECTION_CACHE, "wb") as f:
        content = json.dumps(data, indent=4)
        f.write(content.encode("utf-8"))


def get_selection_from_cache() -> Tuple[datetime, datetime]:
    if not os.path.exists(DATE_RANGE_SELECTION_CACHE):
        return datetime.now().date(), datetime.now().date()

    with open(DATE_RANGE_SELECTION_CACHE, "rb") as f:
        content = f.read()
        _selection = json.loads(content)

        preset = _selection.get("preset")

        if preset:
            today = datetime.now().date()
            if preset == DateRangePreset.TODAY:
                return today, today
            elif preset == DateRangePreset.YESTERDAY:
                yesterday = today - timedelta(days=1)
                return yesterday, yesterday
            elif preset == DateRangePreset.THIS_WEEK:
                first_day = today - timedelta(days=today.weekday())
                return first_day, today
            elif preset == DateRangePreset.LAST_7_DAYS:
                last_week = today - timedelta(days=7)
                return last_week, today
            elif preset == DateRangePreset.LAST_14_DAYS:
                two_weeks_ago = today - timedelta(days=14)
                return two_weeks_ago, today
            elif preset == DateRangePreset.THIS_MONTH:
                first_day = today.replace(day=1)
                return first_day, today
            elif preset == DateRangePreset.LAST_30_DAYS:
                thirty_days_ago = today - timedelta(days=30)
                return thirty_days_ago, today

        # Handle custom dates or fallback
        _from_date = (
            datetime.fromisoformat(_selection.get("from_date").replace("Z", "+00:00"))
            if _selection.get("from_date")
            else None
        )
        _to_date = (
            datetime.fromisoformat(_selection.get("to_date").replace("Z", "+00:00"))
            if _selection.get("to_date")
            else None
        )

        return _from_date, _to_date


def get_selected_date_range() -> Tuple[datetime, datetime]:
    global _date_selection_widget, _display_handle

    if _date_selection_widget is None:
        build_widget()

    if _display_handle is None:
        _display_handle = DisplayHandle()
    _display_handle.display(_date_selection_widget)

    from_date, to_date = get_selection_from_cache()
    # from_date = _date_selection_widget.children[0].children[0].value
    # to_date = _date_selection_widget.children[0].children[1].value

    if from_date:
        from_date = datetime.combine(from_date, time(0, 0, 0))

    if to_date:
        to_date = datetime.combine(to_date, time(23, 59, 59))

    return from_date, to_date
