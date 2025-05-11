from calendar_ipynb.meta import get_productive_categories
import pandas as pd
import matplotlib.pyplot as plt
import mplcursors


def show_productivity_piechart(events):
    if not events:
        raise ValueError("No events provided")

    productive_categories = get_productive_categories()
    productive_events = [
        x
        for x in events
        if any(
            [
                category[0] in productive_categories
                for category in x.get("categories", [])
            ]
        )
    ]

    other_events = [
        x
        for x in events
        if not any(
            [
                category[0] in productive_categories
                for category in x.get("categories", [])
            ]
        )
        and x.get("categories")[0][0] not in ("time-left", "sleep")
    ]

    sleep_events = [x for x in events if x.get("categories")[0][0] == "sleep"]

    time_left_event = next(
        (x for x in events if x.get("categories")[0][0] == "time-left"),
        None,
    )

    if not productive_events and not other_events:
        raise ValueError("No productive or other events provided")

    # Calculate durations in hours
    sleep_hours = sum(event["duration_min"] for event in sleep_events) / 60
    productive_hours = sum(event["duration_min"] for event in productive_events) / 60
    other_hours = sum(event["duration_min"] for event in other_events) / 60
    time_left_hours = time_left_event["duration_min"] / 60 if time_left_event else 0

    # Create data for pie chart
    data = [
        {"category": "Productive", "duration": productive_hours},
        {"category": "Other", "duration": other_hours},
        {"category": "Time Left", "duration": time_left_hours},
        {"category": "Sleep", "duration": sleep_hours},
    ]

    # Create DataFrame
    df = pd.DataFrame(data)
    category_totals = df.groupby("category")["duration"].sum()

    # Create figure and axis
    pie_fig, pie_ax = plt.subplots(figsize=(10, 8))

    # Create pie chart
    wedges, texts, autotexts = pie_ax.pie(
        category_totals,
        labels=category_totals.index,
        autopct="%1.1f%%",
        pctdistance=0.85,
        colors=[
            "#2ecc71",
            "#e74c3c",
            "#0356fc",
            "#95a5a6",
        ],  # Green for productive, Red for other, Gray for time left
    )

    # Add a title
    plt.title("Daily Productivity Distribution")

    # Add legend
    plt.legend(
        wedges,
        category_totals.index,
        title="Categories",
        bbox_to_anchor=(1.05, 1),
        loc="upper left",
    )

    # Add a text box for displaying clicked wedge info
    info_text = pie_ax.text(
        0.5,
        -0.05,
        "Click a wedge to see details",
        transform=pie_ax.transAxes,
        ha="center",
        va="center",
        bbox=dict(facecolor="white", alpha=0.8, edgecolor="gray"),
    )

    # Add tooltips
    pie_cursor = mplcursors.cursor(pie_ax, hover=True)

    @pie_cursor.connect("add")
    def on_add(sel):
        wedge_idx = wedges.index(sel.artist)
        category = category_totals.index[wedge_idx]
        hours = category_totals[category]
        percentage = (hours / category_totals.sum()) * 100
        sel.annotation.set_text(
            f"Category: {category}\nHours: {hours:.2f}\nPercentage: {percentage:.1f}%"
        )

    # Function to handle click events
    def on_click(event):
        if event.inaxes != pie_ax:
            return

        for wedge_idx, wedge in enumerate(wedges):
            if wedge.contains_point([event.x, event.y]):
                category = category_totals.index[wedge_idx]
                hours = category_totals[wedge_idx]
                percentage = (hours / category_totals.sum()) * 100
                info_text.set_text(
                    f"Category: {category}\nHours: {hours:.2f}\nPercentage: {percentage:.1f}%"  # noqa: E501
                )
                pie_fig.canvas.draw_idle()
                return

    pie_fig.canvas.mpl_connect("button_press_event", on_click)

    plt.tight_layout()
    plt.show()
