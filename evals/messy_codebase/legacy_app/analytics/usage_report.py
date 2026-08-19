from io import StringIO


def render_usage(sessions, metrics):
    """Render sessions as pipe-separated text with a header line."""
    sink = StringIO()
    sink.write("|".join(metrics))
    sink.write("\n")
    for session in sessions:
        readings = []
        for metric in metrics:
            if metric == "tenant":
                continue
            reading = str(session.get(metric, ""))
            if "|" in reading:
                reading = "/" + reading + "/"
            readings.append(reading)
        sink.write("|".join(readings))
        sink.write("\n")
    return sink.getvalue()
