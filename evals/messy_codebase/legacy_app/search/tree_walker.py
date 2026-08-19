class TreeCounter:
    """Counts tree nodes by kind using an explicit work stack."""

    def walk(self, node):
        counts = {}
        stack = [node]
        while stack:
            current = stack.pop()
            if current.kind == "leaf":
                counts["leaf"] = counts.get("leaf", 0) + 1
            else:
                counts["branch"] = counts.get("branch", 0) + 1
                stack.extend(reversed(current.children))
        return counts
