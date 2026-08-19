"""Shared fixture sources for slasht tests.

Each pair (X, X_CLONE) is structurally identical: same statement kinds in the same
order, differing only in identifiers, literals, comments, and whitespace.
"""

PY_A = '''\
def process_order(order, inventory):
    """Ship an order if stock allows."""
    # find the line item
    item = inventory.find(order.sku)
    if item is None:
        return {"status": "missing"}
    if item.count < order.qty:
        shortage = order.qty - item.count
        return {"status": "backorder", "shortage": shortage}
    item.count -= order.qty
    log.info("shipped %s", order.sku)
    return {"status": "ok", "remaining": item.count}
'''

# Same skeleton as PY_A; every name, string, and comment differs.
PY_CLONE = '''\
def fulfil_request(basket, warehouse):
    """Release a basket when stock allows."""
    # locate the product row
    row = warehouse.lookup(basket.code)
    if row is None:
        return {"state": "absent"}
    if row.stock < basket.amount:
        gap = basket.amount - row.stock
        return {"state": "deferred", "gap": gap}
    row.stock -= basket.amount
    audit.debug("released %s", basket.code)
    return {"state": "done", "left": row.stock}
'''

# Same as PY_A; only literal values change (docstring, dict values, log format).
PY_LITERALS_ONLY = '''\
def process_order(order, inventory):
    """Dispatch an order when available."""
    # find the line item
    item = inventory.find(order.sku)
    if item is None:
        return {"status": "gone"}
    if item.count < order.qty:
        shortage = order.qty - item.count
        return {"status": "defer", "shortage": shortage}
    item.count -= order.qty
    log.info("dispatched %d", order.sku)
    return {"status": "fine", "remaining": item.count}
'''

# PY_A plus one extra branch: a genuine structural addition.
PY_ADDED_BRANCH = '''\
def process_order(order, inventory):
    """Ship an order if stock allows."""
    # find the line item
    item = inventory.find(order.sku)
    if item is None:
        return {"status": "missing"}
    if order.rush:
        log.info("rush shipment requested")
    if item.count < order.qty:
        shortage = order.qty - item.count
        return {"status": "backorder", "shortage": shortage}
    item.count -= order.qty
    log.info("shipped %s", order.sku)
    return {"status": "ok", "remaining": item.count}
'''

# PY_A with swapped operators (- -> +, -= -> +=): value-level skeleton change.
PY_OPERATOR_SWAP = '''\
def process_order(order, inventory):
    """Ship an order if stock allows."""
    # find the line item
    item = inventory.find(order.sku)
    if item is None:
        return {"status": "missing"}
    if item.count < order.qty:
        shortage = order.qty + item.count
        return {"status": "backorder", "shortage": shortage}
    item.count += order.qty
    log.info("shipped %s", order.sku)
    return {"status": "ok", "remaining": item.count}
'''

GO_A = """\
package tally

func Sum(values []int) int {
\ttotal := 0
\tfor _, v := range values {
\t\tif v > 100 {
\t\t\ttotal += v / 2
\t\t} else {
\t\t\ttotal += v
\t\t}
\t}
\treturn total
}
"""

GO_CLONE = """\
package accumulation

func Fold(numbers []int) int {
\trunning := 0
\tfor _, item := range numbers {
\t\tif item > 50 {
\t\t\trunning += item / 3
\t\t} else {
\t\t\trunning += item
\t\t}
\t}
\treturn running
}
"""

CS_A = """\
using System.Text;

public class Mailer
{
    public string Render(string recipient, int code)
    {
        var builder = new StringBuilder();
        if (code == 0)
        {
            builder.Append("none");
        }
        else
        {
            builder.Append(recipient);
        }
        return builder.ToString();
    }
}
"""

CS_CLONE = """\
using System.Text;

public class Notifier
{
    public string Build(string target, int status)
    {
        var buffer = new StringBuilder();
        if (status == 0)
        {
            buffer.Append("empty");
        }
        else
        {
            buffer.Append(target);
        }
        return buffer.ToString();
    }
}
"""

NOISE_FIB = """\
def fib_stream(limit):
    sequence = []
    previous, current = 0, 1
    while len(sequence) < limit:
        sequence.append(current)
        previous, current = current, previous + current
    return sequence
"""

NOISE_CONFIG = """\
import json
from pathlib import Path

def load_config(path, overrides=None):
    raw = Path(path).read_text()
    settings = json.loads(raw)
    for key, value in (overrides or {}).items():
        settings[key] = value
    return settings
"""
