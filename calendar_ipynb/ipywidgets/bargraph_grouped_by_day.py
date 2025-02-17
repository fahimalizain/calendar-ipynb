import logging
import pandas as pd
import matplotlib.pyplot as plt
import mplcursors

logger = logging.getLogger(__name__)


def show_bargraph(events):
    if not events:
        raise ValueError("No events provided")

    # Assuming 'events' is your list of calendar events
    # First, let's create a DataFrame with the required information
    data = []
    for event in events:
        date = pd.to_datetime(event["start"]["dateTime"]).date()
        if not len(event["categories"]):
            continue

        # We only consider the first category for each event
        category = event["categories"][0][0].split("/")[0]
        data.append(
            {"date": date, "category": category, "duration": event["duration_min"] / 60}
        )

    # Create DataFrame
    df = pd.DataFrame(data)

    # Pivot the data to create stacked bar format
    pivot_df = df.pivot_table(
        index="date", columns="category", values="duration", aggfunc="sum"
    ).fillna(0)

    # Create the stacked bar plot
    ax = pivot_df.plot(kind="bar", stacked=True, figsize=(12, 6), rot=45)
    # Format dates on x-axis
    ax.set_xticklabels([d.strftime("%Y-%m-%d") for d in pivot_df.index])

    # Add cursor/tooltip functionality
    cursor = mplcursors.cursor(ax, hover=True)

    @cursor.connect("add")
    def on_add(sel):
        try:
            bar = sel.artist
            category = bar.get_label()

            # Get the date index from x-coordinate
            date_idx = int(sel.target[0])
            date = pivot_df.index[date_idx]

            # Get height directly from the bar object
            value = bar.patches[date_idx].get_height()

            sel.annotation.set_text(
                f"Date: {date}\nCategory: {category}\nHours: {value:.2f}"
            )
        except Exception:
            # Fallback simple annotation
            sel.annotation.set_text(f"Value: {sel.target[1]:.2f}")

    # Customize the plot
    plt.title("Daily Time Spent by Category")
    plt.xlabel("Date")
    plt.ylabel("Duration (hours)")
    plt.legend(title="Categories", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()

    # Show the plot
    plt.show()


"""
    @cursor.connect("add")
    def on_add(sel):
        try:
            # Get the artist (bar) and its label (category)
            bar = sel.artist
            category = bar.get_label()

            # Get the date index from x-coordinate
            date_idx = int(sel.target[0])
            date = pivot_df.index[date_idx]

            # Get the actual value for this category on this date
            value = pivot_df.loc[date, category]

            sel.annotation.set_text(
                f"Date: {date}\nCategory: {category}\nHours: {value:.2f}"
            )
        except Exception:
            # Fallback simple annotation
            sel.annotation.set_text(f"Value: {sel.target[1]:.2f}")
"""


"""
    @cursor.connect("add")
    def on_add(sel):
        try:
            # Get the artist (bar) that was hovered
            bar = sel.artist
            # Get the index of the hovered bar
            bar_idx = bar.get_label()
            # Get the height at the hover point
            height = sel.target[1]
            logger.info(f"Hovered over bar {bar_idx} at height {height}", bar)

            # Find the date (x-axis value)
            date_idx = int(sel.target[0])
            date = pivot_df.index[date_idx]

            sel.annotation.set_text(
                f"Date: {date}\nCategory: {bar_idx}\nHours: {height:.2f}"
            )
        except Exception:
            # Fallback simple annotation
            sel.annotation.set_text(f"Value: {sel.target[1]:.2f}")
"""

"""
def _on_add_old(sel):
    # Get the bar's coordinates
    x, y = sel.target
    # Calculate which category and date based on the x coordinate
    date_idx = int(x)
    date = pivot_df.index[date_idx]

    # Find which stack segment was clicked
    y_sums = pivot_df.iloc[date_idx].cumsum()
    category_idx = y_sums.searchsorted(y, side="right")
    category = pivot_df.columns[category_idx]

    # Get the actual value for this segment
    value = pivot_df.iloc[date_idx][category]

    sel.annotation.set_text(
        f"Date: {date}\nCategory: {category}\nHours: {value:.2f}"
    )
"""
