import json
import os
from typing import List, TypedDict

import ipywidgets as widgets
from IPython.display import display

from calendar_ipynb.utils import get_temp_path

from ..events import fetch_calendars


class Calendar(TypedDict):
    id: str
    summary: str


class EmailCalendarMap(TypedDict):
    email: str
    calendars: List[Calendar]


CALENDAR_SELECTION_CACHE = get_temp_path("calendar_selection.json")
_calendar_selection_widget = None
_calendar_map = None


def select_calendars(EMAIL_IDS: List[str]):
    global _calendar_selection_widget, _calendar_map

    calendar_map = []
    for email in EMAIL_IDS:
        calendars = fetch_calendars(email)
        calendar_map.append(EmailCalendarMap(email=email, calendars=calendars))

    _selection = get_selection_from_cache()

    email_widgets = []
    for _map in calendar_map:
        email = _map["email"]
        calendars = _map["calendars"]

        # Create email header
        email_header = widgets.HTML(value=f"<b>{email}</b>")

        # Create calendar checkboxes
        calendar_checkboxes = [
            widgets.Checkbox(
                value=(True if cal["id"] in _selection.get(email, []) else False),
                description=cal["summary"],
            )
            for cal in calendars
        ]

        # Group calendars with indentation
        calendar_group = widgets.VBox(
            calendar_checkboxes,
            layout=widgets.Layout(
                margin="0 0 0 20px"
            ),  # Add left margin for indentation
        )

        for _checkbox in calendar_checkboxes:
            _checkbox.observe(cache_selection)

        # Combine email header and its calendars
        email_group = widgets.VBox([email_header, calendar_group])

        email_widgets.append(email_group)

    # Create final widget containing all email groups
    _calendar_selection_widget = widgets.VBox(email_widgets)
    _calendar_map = calendar_map

    # Display the widget
    display(_calendar_selection_widget)


def cache_selection(*args, **kwargs):
    selection = get_selected_calendars()

    with open(CALENDAR_SELECTION_CACHE, "wb") as f:
        content = json.dumps(selection, indent=4)
        f.write(content.encode("utf-8"))


def get_selection_from_cache():
    # Check if cache file exists
    if not os.path.exists(CALENDAR_SELECTION_CACHE):
        return {}

    with open(CALENDAR_SELECTION_CACHE, "rb") as f:
        content = f.read()
        return json.loads(content)


# To get values later:
def get_selected_calendars():
    global _calendar_selection_widget, _calendar_map

    selected = {}
    email_list = [x["email"] for x in _calendar_map]

    for _map in _calendar_map:
        email = _map["email"]
        calendars = _map["calendars"]

        selected[email] = [
            cal["id"]
            for cal, checkbox in zip(
                calendars,
                _calendar_selection_widget.children[email_list.index(email)]
                .children[1]
                .children,
            )
            if checkbox.value
        ]

        if not selected[email]:
            selected.pop(email)

    return selected
