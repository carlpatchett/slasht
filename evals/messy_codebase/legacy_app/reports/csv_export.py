from io import StringIO


def write_csv(rows, headers):
    """Render rows as CSV text with a header line."""
    buffer = StringIO()
    buffer.write(",".join(headers))
    buffer.write("\n")
    for row in rows:
        cells = []
        for header in headers:
            value = str(row.get(header, ""))
            if "," in value:
                value = '"' + value + '"'
            cells.append(value)
        buffer.write(",".join(cells))
        buffer.write("\n")
    return buffer.getvalue()
