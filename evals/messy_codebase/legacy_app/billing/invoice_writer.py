from io import StringIO


def build_statement(records, columns):
    """Render records as semicolon-separated text with a header line."""
    out = StringIO()
    out.write(";".join(columns))
    out.write("\n")
    for record in records:
        fields = []
        for column in columns:
            text = str(record.get(column, ""))
            if ";" in text:
                text = "'" + text + "'"
            fields.append(text)
        out.write(";".join(fields))
        out.write("\n")
    return out.getvalue()
