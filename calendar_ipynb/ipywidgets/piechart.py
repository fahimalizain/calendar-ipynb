import logging
import pandas as pd
import matplotlib.pyplot as plt
import mplcursors

logger = logging.getLogger(__name__)


def show_piechart(events):
    if not events:
        raise ValueError("No events provided")

    # Create data list with category and duration
    data = []
    for event in events:
        if not len(event["categories"]):
            continue

        # We only consider the first category for each event
        category = event["categories"][0][0].split("/")[0]
        data.append({"category": category, "duration": event["duration_min"] / 60})

    # Create DataFrame
    df = pd.DataFrame(data)

    # Group by category and sum durations
    category_totals = df.groupby("category")["duration"].sum()

    # Create figure and axis
    fig, ax = plt.subplots(figsize=(10, 8))

    # Create pie chart
    wedges, texts, autotexts = ax.pie(
        category_totals,
        labels=category_totals.index,
        autopct="%1.1f%%",
        pctdistance=0.85,
    )

    # Add a title
    plt.title("Total Time Distribution by Category")

    # Add legend
    plt.legend(
        wedges,
        category_totals.index,
        title="Categories",
        bbox_to_anchor=(1.05, 1),
        loc="upper left",
    )

    # Add tooltips
    cursor = mplcursors.cursor(wedges, hover=True)

    @cursor.connect("add")
    def on_add(sel):
        category = category_totals.index[wedges.index(sel.artist)]
        hours = category_totals[category]
        percentage = (hours / category_totals.sum()) * 100
        sel.annotation.set_text(
            f"Category: {category}\nHours: {hours:.2f}\nPercentage: {percentage:.1f}%"
        )

    plt.tight_layout()
    plt.show()
