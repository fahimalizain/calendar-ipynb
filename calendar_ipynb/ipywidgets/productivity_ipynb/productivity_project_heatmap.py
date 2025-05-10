import datetime
import logging
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger(__name__)


def show_productivity_project_heatmap(events):
    if not events:
        raise ValueError("No events provided")

    # Create data list with date, category and duration
    data = []
    for event in events:
        if not len(event["categories"]):
            continue

        # We only consider the first category for each event
        category = event["categories"][0][0].split("/")[0]
        start_datetime = datetime.datetime.fromisoformat(event["start"]["dateTime"])
        data.append(
            {
                "date": start_datetime.date(),
                "category": category,
                "duration": event["duration_min"] / 60,
            }
        )

    # Create DataFrame
    df = pd.DataFrame(data)

    # Pivot the data to get categories as rows and dates as columns
    daily_df = df.pivot_table(
        index="category", columns="date", values="duration", aggfunc="sum", fill_value=0
    )

    # Create figure and axis with larger size
    plt.figure(figsize=(15, 8))

    # Create heatmap
    sns.heatmap(
        daily_df,
        cmap="YlOrRd",
        robust=True,
        fmt=".1f",
        cbar_kws={"label": "Hours"},
    )

    # Customize the plot
    plt.title("Daily Time Spent by Category")
    plt.xlabel("Date")
    plt.ylabel("Category")

    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45, ha="right")

    # Add tooltips
    # cursor = mplcursors.cursor(hover=True)

    # @cursor.connect("add")
    # def on_add(sel):
    #     # Get the row and column indices
    #     row_idx = int(sel.target.index[0])
    #     col_idx = int(sel.target.index[1])

    #     # Get the corresponding category and date
    #     category = daily_df.index[row_idx]
    #     date = daily_df.columns[col_idx]
    #     value = daily_df.iloc[row_idx, col_idx]

    #     sel.annotation.set_text(
    #         f"Date: {date}\nCategory: {category}\nHours: {value:.2f}"
    #     )

    plt.tight_layout()
    plt.show()
