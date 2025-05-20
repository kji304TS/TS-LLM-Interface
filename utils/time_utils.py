from datetime import datetime, timedelta, timezone

def calculate_dates_from_preset(preset: str) -> tuple[str, str]:
    """
    Calculates start and end datetime strings based on a preset.
    Returns (start_date_str, end_date_str) in "YYYY-MM-DD HH:MM" format.
    All calculations are based on current UTC time.
    """
    now_utc = datetime.now(timezone.utc)
    start_dt = None
    end_dt = now_utc # Default end time is now for most presets

    if preset == "last_hour":
        start_dt = now_utc - timedelta(hours=1)
    elif preset == "last_8_hours":
        start_dt = now_utc - timedelta(hours=8)
    elif preset == "previous_8_hours":
        end_dt = now_utc - timedelta(hours=8)
        start_dt = end_dt - timedelta(hours=8)
    elif preset == "yesterday":
        yesterday_date = now_utc.date() - timedelta(days=1)
        start_dt = datetime(yesterday_date.year, yesterday_date.month, yesterday_date.day, 0, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime(yesterday_date.year, yesterday_date.month, yesterday_date.day, 23, 59, 59, tzinfo=timezone.utc) # End of yesterday
    elif preset == "last_7_days":
        start_dt = now_utc - timedelta(days=7)
        # end_dt is already now_utc
    else:
        # Default or fallback: last 24 hours if preset is unknown
        # Or you could raise an error: raise ValueError(f"Unknown timeframe preset: {preset}")
        print(f"Warning: Unknown timeframe preset '{preset}'. Defaulting to last 24 hours.")
        start_dt = now_utc - timedelta(days=1)

    # Format to "YYYY-MM-DD HH:MM"
    # Ensure start_dt is not None (it should be set by the logic above)
    if start_dt is None: # Should ideally not happen if all presets are handled
        start_dt = now_utc - timedelta(days=1) # Fallback safety
        
    start_date_str = start_dt.strftime("%Y-%m-%d %H:%M")
    end_date_str = end_dt.strftime("%Y-%m-%d %H:%M")

    return start_date_str, end_date_str

if __name__ == '__main__':
    # Test the function
    presets_to_test = ["last_hour", "last_8_hours", "previous_8_hours", "yesterday", "last_7_days", "unknown_preset"]
    for p in presets_to_test:
        s, e = calculate_dates_from_preset(p)
        print(f"Preset: {p}\n  Start: {s}\n  End:   {e}\n") 