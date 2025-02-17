import json
import os
from datetime import datetime, time, timedelta
from typing import Tuple

import ipywidgets as widgets
from IPython.display import DisplayHandle

from calendar_ipynb.utils import get_temp_path

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

    # Create button handlers
    def set_today(b):
        today = datetime.now().date()
        from_date_picker.value = today
        to_date_picker.value = today

    def set_yesterday(b):
        yesterday = (datetime.now() - timedelta(days=1)).date()
        from_date_picker.value = yesterday
        to_date_picker.value = yesterday

    def set_this_week(b):
        today = datetime.now().date()
        first_day = today - timedelta(days=today.weekday())
        from_date_picker.value = first_day
        to_date_picker.value = today

    def set_last_7_days(b):
        today = datetime.now().date()
        last_week = (datetime.now() - timedelta(days=7)).date()
        from_date_picker.value = last_week
        to_date_picker.value = today

    def set_last_14_days(b):
        today = datetime.now().date()
        two_weeks_ago = (datetime.now() - timedelta(days=14)).date()
        from_date_picker.value = two_weeks_ago
        to_date_picker.value = today

    def set_this_month(b):
        today = datetime.now().date()
        first_day = today.replace(day=1)
        from_date_picker.value = first_day
        to_date_picker.value = today

    # Attach handlers to buttons
    today_btn.on_click(set_today)
    yesterday_btn.on_click(set_yesterday)
    this_week_btn.on_click(set_this_week)
    last_7_days_btn.on_click(set_last_7_days)
    last_14_days_btn.on_click(set_last_14_days)
    this_month_btn.on_click(set_this_month)

    # Create horizontal button container
    buttons = widgets.HBox(
        [
            today_btn,
            yesterday_btn,
            this_week_btn,
            last_7_days_btn,
            last_14_days_btn,
            this_month_btn,
        ]
    )

    # Combine date pickers and buttons
    _date_selection_widget = widgets.VBox(
        [widgets.HBox([from_date_picker, to_date_picker]), buttons]
    )

    from_date_picker.observe(cache_selection)
    to_date_picker.observe(cache_selection)


def cache_selection(*args, **kwargs):
    from_date, to_date = get_selected_date_range()
    data = {}
    if from_date:
        data["from_date"] = from_date.isoformat() + "Z"

    if to_date:
        data["to_date"] = to_date.isoformat() + "Z"

    with open(DATE_RANGE_SELECTION_CACHE, "wb") as f:
        content = json.dumps(data, indent=4)
        f.write(content.encode("utf-8"))


def get_selection_from_cache() -> Tuple[datetime, datetime]:
    # Check if cache file exists
    if not os.path.exists(DATE_RANGE_SELECTION_CACHE):
        return {}

    with open(DATE_RANGE_SELECTION_CACHE, "rb") as f:
        content = f.read()
        _selection = json.loads(content)

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

    from_date = _date_selection_widget.children[0].children[0].value
    to_date = _date_selection_widget.children[0].children[1].value

    if from_date:
        from_date = datetime.combine(from_date, time(0, 0, 0))

    if to_date:
        to_date = datetime.combine(to_date, time(23, 59, 59))

    return from_date, to_date
