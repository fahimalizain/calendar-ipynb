import datetime
import logging
import pandas as pd
import matplotlib.pyplot as plt
import mplcursors

logger = logging.getLogger(__name__)


def show_productivity_piechart(events):
    if not events:
        raise ValueError("No events provided")

    from_date = datetime.date.max
    to_date = datetime.date.min

    # Create data list with category and duration
    data = []
    for event in events:
        if not len(event["categories"]):
            continue

        # We only consider the first category for each event
        category = event["categories"][0][0].split("/")[0]
        data.append({"category": category, "duration": event["duration_min"] / 60})

        start_datetime = datetime.datetime.fromisoformat(event["start"]["dateTime"])
        from_date = min(from_date, start_datetime.date())
        to_date = max(to_date, start_datetime.date())

    # Create DataFrame
    df = pd.DataFrame(data)

    # Group by category and sum durations
    category_totals = df.groupby("category")["duration"].sum()

    # Create figure and axis
    pie_fig, pie_ax = plt.subplots(figsize=(10, 8))

    # Create pie chart
    wedges, texts, autotexts = pie_ax.pie(
        category_totals,
        labels=category_totals.index,
        autopct="%1.1f%%",
        pctdistance=0.85,
    )

    # Add a title
    plt.title(f"Productive Time spent by Category: {from_date} to {to_date}")

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
        print("Hover detected", sel.artist)
        # Get the index of the selected wedge
        wedge_idx = wedges.index(sel.artist)
        category = category_totals.index[wedge_idx]
        hours = category_totals[category]
        percentage = (hours / category_totals.sum()) * 100
        sel.annotation.set_text(
            f"Category: {category}\nHours: {hours:.2f}\nPercentage: {percentage:.1f}%"
        )

    # Function to handle click events
    def on_click(event):
        if event.inaxes != pie_ax:  # Ignore clicks outside the axes
            return

        # Check which wedge was clicked
        for wedge_idx, wedge in enumerate(wedges):
            if wedge.contains_point([event.x, event.y]):
                category = category_totals.index[wedge_idx]
                hours = category_totals[wedge_idx]
                percentage = (hours / category_totals.sum()) * 100
                info_text.set_text(
                    f"Category: {category}\nHours: {hours:.2f}\nPercentage: {percentage:.1f}%"  # noqa: E501
                )
                pie_fig.canvas.draw_idle()  # Update the canvas
                return

    # Connect the click event to the figure
    pie_fig.canvas.mpl_connect("button_press_event", on_click)

    plt.tight_layout()
    plt.show()
