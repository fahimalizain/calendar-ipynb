import datetime
import logging
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger(__name__)


def show_productivity_weekday_heatmap(events):
    if not events:
        raise ValueError("No events provided")

    # Initialize a DataFrame with all hours for each weekday
    weekdays = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    hours = list(range(24))

    # Create empty DataFrame with 0s
    df = pd.DataFrame(
        float(0),
        index=hours,
        columns=weekdays,
    )

    # Fill in the hours with actual data
    for event in events:
        start = datetime.datetime.fromisoformat(event["start"]["dateTime"])
        end = datetime.datetime.fromisoformat(event["end"]["dateTime"])

        # Handle events spanning multiple days
        current_date = start.date()
        while current_date <= end.date():
            weekday = current_date.strftime("%A")  # Get day name

            for hour in range(24):
                hour_start = datetime.datetime.combine(
                    current_date, datetime.time(hour), tzinfo=start.tzinfo
                )
                hour_end = hour_start + datetime.timedelta(hours=1)

                # Calculate overlap between event and current hour
                overlap_start = max(
                    start if current_date == start.date() else hour_start, hour_start
                )
                overlap_end = min(
                    end if current_date == end.date() else hour_end, hour_end
                )

                if overlap_start < overlap_end:
                    overlap_hours = (overlap_end - overlap_start).total_seconds() / 3600
                    df.at[hour, weekday] += overlap_hours

            current_date += datetime.timedelta(days=1)

    # Average the hours by number of weeks in the data
    num_weeks = len(
        set(
            datetime.datetime.fromisoformat(event["start"]["dateTime"]).strftime("%V")
            for event in events
        )
    )
    df = df / num_weeks

    # Create figure and axis
    plt.figure(figsize=(12, 10))

    # Create heatmap
    sns.heatmap(
        df,
        cmap="YlOrRd",
        robust=True,
        fmt=".2f",
        cbar_kws={"label": "Average Hours"},
        yticklabels=[f"{h:02d}:00" for h in range(24)],
    )

    # Customize the plot
    plt.title("Average Weekly Productivity by Hour and Day")
    plt.xlabel("Day of Week")
    plt.ylabel("Hour of Day")

    # Add tooltips
    # cursor = mplcursors.cursor(hover=True)

    # @cursor.connect("add")
    # def on_add(sel):
    #     row_idx = int(sel.target.index[0])
    #     col_idx = int(sel.target.index[1])

    #     hour = df.index[row_idx]
    #     weekday = df.columns[col_idx]
    #     value = df.iloc[row_idx, col_idx]

    #     sel.annotation.set_text(
    #         f"Day: {weekday}\nHour: {hour:02d}:00\nAvg Hours: {value:.2f}"
    #     )

    plt.tight_layout()
    plt.show()
