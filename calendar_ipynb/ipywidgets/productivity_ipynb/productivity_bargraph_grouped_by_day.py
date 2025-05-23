import logging
import pandas as pd
import matplotlib.pyplot as plt
import mplcursors


logger = logging.getLogger(__name__)


def show_productivity_bargraph_grouped_by_day(events):
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
    all_dates = pd.date_range(
        start=pivot_df.index.min(), end=pivot_df.index.max(), freq="D"
    )
    pivot_df = pivot_df.reindex(all_dates, fill_value=0)

    # Create the stacked bar plot
    ax = pivot_df.plot(kind="bar", stacked=True, figsize=(15, 6), rot=45)
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
