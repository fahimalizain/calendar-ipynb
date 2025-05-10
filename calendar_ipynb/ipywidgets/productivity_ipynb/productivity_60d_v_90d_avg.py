import pandas as pd
import matplotlib.pyplot as plt


def show_productivity_line_60d_v_30d_avg(events: list):
    """
    Function to show productivity line chart for 60 days vs 30 days average.
    Shows long term trend growth in daily productive hours.
    """
    if not events:
        raise ValueError("No events provided")

    # Create DataFrame with daily total durations
    data = []
    for event in events:
        date = pd.to_datetime(event["start"]["dateTime"]).date()
        if not event["categories"]:
            continue
        data.append(
            {"date": date, "duration": event["duration_min"] / 60}  # Convert to hours
        )

    df = pd.DataFrame(data)

    # Group by date and sum durations
    daily_totals = df.groupby("date")["duration"].sum().reset_index()
    daily_totals.set_index("date", inplace=True)
    daily_totals.sort_index(inplace=True)

    # Get the last 30 days date range
    last_date = daily_totals.index.max()
    start_date = last_date - pd.Timedelta(days=30)

    # Calculate moving averages
    ma_60d = daily_totals["duration"].rolling(window=60, min_periods=1).mean()
    ma_30d = daily_totals["duration"].rolling(window=30, min_periods=1).mean()

    # Filter data for last 30 days
    mask = daily_totals.index >= start_date
    daily_totals_30d = daily_totals[mask]
    ma_60d_30d = ma_60d[mask]
    ma_30d_30d = ma_30d[mask]

    # Create the plot
    plt.figure(figsize=(15, 6))
    plt.plot(
        daily_totals_30d.index, ma_60d_30d, label="60-day Moving Average", linewidth=2
    )
    plt.plot(
        daily_totals_30d.index, ma_30d_30d, label="30-day Moving Average", linewidth=2
    )

    # Customize the plot
    plt.title("Productivity Trends: 60-day vs 30-day Moving Averages")
    plt.xlabel("Date")
    plt.ylabel("Average Daily Hours")
    plt.legend(loc="upper left")
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Show the plot
    plt.show()
