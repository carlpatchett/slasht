class NodeVisitor:
    """Base class that walks a tree, dispatching on node kind."""

    def walk(self, node):
        results = []
        for child in node.children:
            if child.kind == "leaf":
                results.append(self.visit_leaf(child))
            else:
                results.extend(self.visit_branch(child))
        return results

    def visit_leaf(self, leaf):
        raise NotImplementedError

    def visit_branch(self, branch):
        raise NotImplementedError
