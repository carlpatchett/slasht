"""Deterministic generator for the scaled eval fixture.

Emits "meridian" — a growth-stage SaaS monorepo (three Python services, Go
tooling, C# jobs) with seven planted structural-clone families (rename-only
copies: skeleton similarity exactly 1.0 within a family) and ~20 noise modules
with genuinely distinct shapes. Pure function of the templates: identical
output on every run. Returns the ground truth alongside.

The point: big enough that an agent cannot cheaply read everything, so the
baseline arm must sample (hurting recall) while the augmented arm starts from
find_duplicate_groups' map.
"""

from __future__ import annotations

import json
from pathlib import Path

# ----------------------------------------------------------------------
# Python family templates (rename/literal-only variation per instance)

HANDLER = '''\
import logging

from platform.errors import ConflictError, NotFoundError
from platform.http.filters import parse_filters

logger = logging.getLogger(__name__)


class {cls}:
    """HTTP request handlers for {plural}."""

    def __init__(self, repository, validator):
        self.repository = repository
        self.validator = validator

    def list(self, query_params):
        page = max(int(query_params.get("page", 1)), 1)
        size = min(int(query_params.get("size", 25)), {size_cap})
        offset = (page - 1) * size
        filters = parse_filters(query_params, allowed={allowed})
        rows = self.repository.fetch_many(offset=offset, limit=size, filters=filters)
        total = self.repository.count(filters=filters)
        return {{
            "items": [self._present(row) for row in rows],
            "page": page,
            "size": size,
            "total": total,
        }}

    def get(self, ident):
        row = self.repository.fetch_one(ident)
        if row is None:
            raise NotFoundError("{missing}")
        return self._present(row)

    def create(self, payload):
        cleaned = self.validator.check(payload, required={required})
        if self.repository.exists(cleaned["{key}"]):
            raise ConflictError("{conflict}")
        row = self.repository.insert(cleaned)
        logger.info("{created_log}", extra={{"entity": row["{key}"]}})
        return self._present(row)

    def update(self, ident, payload):
        current = self.repository.fetch_one(ident)
        if current is None:
            raise NotFoundError("{missing}")
        cleaned = self.validator.check(payload, partial=True)
        row = self.repository.update(ident, cleaned)
        logger.info("{updated_log}")
        return self._present(row)

    def delete(self, ident):
        removed = self.repository.delete(ident)
        if removed is None:
            raise NotFoundError("{missing}")
        logger.info("{deleted_log}")
        return {{"deleted": ident, "entity": removed["{key}"]}}

    def _present(self, row):
        presented = dict(row)
        presented["state"] = str(presented.get("state", "{state_default}"))
        presented["href"] = "/{plural}/" + str(presented["{key}"])
        return presented
'''

REPOSITORY = '''\
import logging

logger = logging.getLogger(__name__)


class {cls}:
    """SQL-backed store for {plural}."""

    def __init__(self, pool):
        self.pool = pool
        self.table = "{table}"

    def insert(self, values):
        columns = sorted(values)
        placeholders = ", ".join(["?"] * len(columns))
        statement = (
            "INSERT INTO " + self.table
            + " (" + ", ".join(columns) + ") VALUES (" + placeholders + ") RETURNING *"
        )
        with self.pool.transaction() as cursor:
            cursor.execute(statement, [values[c] for c in columns])
            return dict(cursor.fetchone())

    def fetch_one(self, ident):
        statement = "SELECT * FROM " + self.table + " WHERE {id_column} = ?"
        with self.pool.transaction() as cursor:
            cursor.execute(statement, [ident])
            row = cursor.fetchone()
        return dict(row) if row else None

    def fetch_many(self, offset=0, limit=50, filters=None):
        clauses = []
        params = []
        for column, value in (filters or {{}}).items():
            clauses.append(column + " = ?")
            params.append(value)
        statement = "SELECT * FROM " + self.table
        if clauses:
            statement += " WHERE " + " AND ".join(clauses)
        statement += " ORDER BY created_at DESC OFFSET ? LIMIT ?"
        params.extend([offset, limit])
        with self.pool.transaction() as cursor:
            cursor.execute(statement, params)
            return [dict(row) for row in cursor.fetchall()]

    def update(self, ident, values):
        assignments = ", ".join(c + " = ?" for c in sorted(values))
        statement = (
            "UPDATE " + self.table + " SET " + assignments
            + " WHERE {id_column} = ? RETURNING *"
        )
        params = list(values.values()) + [ident]
        with self.pool.transaction() as cursor:
            cursor.execute(statement, params)
            row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def delete(self, ident):
        statement = "DELETE FROM " + self.table + " WHERE {id_column} = ? RETURNING *"
        with self.pool.transaction() as cursor:
            cursor.execute(statement, [ident])
            row = cursor.fetchone()
        return dict(row) if row else None

    def count(self, filters=None):
        statement = "SELECT COUNT(*) AS total FROM " + self.table
        with self.pool.transaction() as cursor:
            cursor.execute(statement)
            row = cursor.fetchone()
        return row["total"] if row else 0

    def exists(self, ident):
        return self.fetch_one(ident) is not None
'''

CLIENT = '''\
import logging
import time

import requests

logger = logging.getLogger(__name__)


class {cls}:
    """HTTP client for the {service} API with retry and backoff."""

    def __init__(self, base_url, token, timeout=10, attempts=4):
        self.base_url = base_url.rstrip("/")
        self.headers = {{"Authorization": "Bearer " + token}}
        self.timeout = timeout
        self.attempts = attempts
        self.session = requests.Session()

    def _request(self, method, path, payload=None):
        url = self.base_url + path
        for attempt in range(self.attempts):
            try:
                response = self.session.request(
                    method,
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                if response.status_code >= 500:
                    raise RuntimeError("upstream unavailable")
                if response.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                return self._unwrap(response)
            except requests.ConnectionError:
                if attempt == self.attempts - 1:
                    raise
                time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError("exhausted retries")

    def _unwrap(self, response):
        if response.status_code == 204:
            return None
        body = response.json()
        if response.status_code >= 400:
            logger.warning("request failed")
            raise RuntimeError("request rejected")
        return body

    def get(self, path):
        return self._request("GET", path)

    def post(self, path, payload):
        return self._request("POST", path, payload)

    def put(self, path, payload):
        return self._request("PUT", path, payload)

    def delete(self, path):
        return self._request("DELETE", path)
'''

CACHE = '''\
import threading
import time
from collections import OrderedDict


class {cls}:
    """Bounded TTL cache for {kind}."""

    def __init__(self, maxsize=256, ttl=60):
        self.maxsize = maxsize
        self.ttl = ttl
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry[0] < time.monotonic():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry[1]

    def set(self, key, value):
        with self._lock:
            self._entries[key] = (time.monotonic() + self.ttl, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.maxsize:
                self._entries.popitem(last=False)

    def drop(self, key):
        with self._lock:
            return self._entries.pop(key, None) is not None

    def clear(self):
        with self._lock:
            self._entries.clear()

    def size(self):
        with self._lock:
            return len(self._entries)
'''

REPORT = '''\
from io import StringIO


def build_{fn}_report(rows, columns, delimiter="{delim}"):
    """Render {title} as delimited text with a header line."""
    buffer = StringIO()
    buffer.write(delimiter.join(columns))
    buffer.write("\\n")
    for row in rows:
        cells = []
        for column in columns:
            if column == "{skip}":
                continue
            value = str(row.get(column, ""))
            if delimiter in value:
                value = '"' + value + '"'
            cells.append(value)
        buffer.write(delimiter.join(cells))
        buffer.write("\\n")
    return buffer.getvalue()
'''

GO_TOOL = '''\
package cmd

import (
\t"flag"
\t"fmt"
\t"os"
\t"path/filepath"
\t"strings"
)

// {Title} walks the workspace and processes matching entries.
func {Title}(arguments []string) error {
\tcommand := flag.NewFlagSet("{name}", flag.ExitOnError)
\troot := command.String("root", ".", "workspace root")
\tpattern := command.String("match", "{pattern}", "entry name filter")
\tdryRun := command.Bool("dry-run", false, "report without acting")
\tif err := command.Parse(arguments); err != nil {
\t\treturn err
\t}
\tvar processed []string
\terr := filepath.Walk(*root, func(path string, info os.FileInfo, err error) error {
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t\tif info.IsDir() {
\t\t\treturn nil
\t\t}
\t\tname := filepath.Base(path)
\t\tif !strings.Contains(name, *pattern) {
\t\t\treturn nil
\t\t}
\t\tif *dryRun {
\t\t\tfmt.Printf("would process %s\\n", path)
\t\t} else {
\t\t\tprocessed = append(processed, path)
\t\t}
\t\treturn nil
\t})
\tif err != nil {
\t\treturn err
\t}
\tif len(processed) == 0 {
\t\treturn fmt.Errorf("no entries matched %s", *pattern)
\t}
\tfmt.Printf("processed %d entries for {name}\\n", len(processed))
\treturn nil
}
'''

CS_JOB = '''\
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Meridian.Jobs
{
    public class {Title}Job
    {
        private readonly IDictionary<string, string> _configuration;
        private readonly IList<string> _failures;

        public {Title}Job(IDictionary<string, string> configuration)
        {
            _configuration = configuration;
            _failures = new List<string>();
        }

        public async Task<int> RunAsync(CancellationToken token)
        {
            var batch = int.Parse(_configuration["batch.size"]);
            var processed = 0;
            foreach (var item in LoadWork(batch))
            {
                if (token.IsCancellationRequested)
                {
                    break;
                }
                try
                {
                    await Handle(item);
                    processed++;
                }
                catch (Exception)
                {
                    _failures.Add(item);
                }
            }
            Console.WriteLine("{DoneLabel}: " + processed + " failures: " + _failures.Count);
            return _failures.Count == 0 ? 0 : 1;
        }

        private IEnumerable<string> LoadWork(int batch)
        {
            for (var index = 0; index < batch; index++)
            {
                yield return "{ItemPrefix}-" + index;
            }
        }

        private async Task Handle(string item)
        {
            await Task.Delay(10);
            if (item.EndsWith("0"))
            {
                throw new InvalidOperationException("{BadItem}");
            }
        }
    }
}
'''

# ----------------------------------------------------------------------
# Family instance tables

HANDLERS = [
    ("services/orders/api/handlers/order_handler.py", "OrderHandler", "orders", "order_id", "sku", 100, ["status", "channel", "created_after"]),
    ("services/orders/api/handlers/shipment_handler.py", "ShipmentHandler", "shipments", "shipment_id", "tracking", 100, ["carrier", "state", "shipped_after"]),
    ("services/orders/api/handlers/refund_handler.py", "RefundHandler", "refunds", "refund_id", "reason", 100, ["status", "method", "requested_after"]),
    ("services/orders/api/handlers/return_handler.py", "ReturnHandler", "returns", "return_id", "rma", 100, ["state", "warehouse", "opened_after"]),
    ("services/orders/api/handlers/webhook_handler.py", "WebhookHandler", "webhooks", "hook_id", "topic", 200, ["event", "state", "delivered_after"]),
    ("services/billing/api/handlers/invoice_handler.py", "InvoiceHandler", "invoices", "invoice_id", "number", 100, ["status", "customer", "issued_after"]),
    ("services/billing/api/handlers/credit_handler.py", "CreditHandler", "credits", "credit_id", "memo", 100, ["reason", "state", "granted_after"]),
    ("services/billing/api/handlers/dispute_handler.py", "DisputeHandler", "disputes", "dispute_id", "case_no", 100, ["phase", "outcome", "opened_after"]),
    ("services/billing/api/handlers/payout_handler.py", "PayoutHandler", "payouts", "payout_id", "reference", 100, ["state", "bank", "settled_after"]),
    ("services/identity/api/handlers/user_handler.py", "UserHandler", "users", "user_id", "email", 100, ["plan", "active", "joined_after"]),
    ("services/identity/api/handlers/session_handler.py", "SessionHandler", "sessions", "session_id", "token", 200, ["device", "revoked", "started_after"]),
    ("services/identity/api/handlers/key_handler.py", "ApiKeyHandler", "keys", "key_id", "prefix", 100, ["scope", "rotated", "created_after"]),
]

REPOSITORIES = [
    ("services/orders/store/order_repository.py", "OrderRepository", "orders", "order_id"),
    ("services/orders/store/shipment_repository.py", "ShipmentRepository", "shipments", "shipment_id"),
    ("services/orders/store/refund_repository.py", "RefundRepository", "refunds", "refund_id"),
    ("services/billing/store/invoice_repository.py", "InvoiceRepository", "invoices", "invoice_id"),
    ("services/billing/store/credit_repository.py", "CreditRepository", "credits", "credit_id"),
    ("services/billing/store/dispute_repository.py", "DisputeRepository", "disputes", "dispute_id"),
    ("services/identity/store/user_repository.py", "UserRepository", "users", "user_id"),
    ("services/identity/store/session_repository.py", "SessionRepository", "sessions", "session_id"),
]

CLIENTS = [
    ("services/orders/clients/intake_client.py", "IntakeClient", "order intake"),
    ("services/orders/clients/tracking_client.py", "TrackingClient", "carrier tracking"),
    ("services/billing/clients/tax_client.py", "TaxClient", "tax engine"),
    ("services/billing/clients/ledger_client.py", "LedgerClient", "general ledger"),
    ("services/identity/clients/email_client.py", "EmailClient", "transactional email"),
    ("services/identity/clients/sms_client.py", "SmsClient", "sms gateway"),
]

CACHES = [
    ("services/orders/caching/quote_cache.py", "QuoteCache", "shipping quotes"),
    ("services/billing/caching/rate_cache.py", "RateCache", "currency rates"),
    ("services/identity/caching/profile_cache.py", "ProfileCache", "user profiles"),
]

REPORTS = [
    ("services/orders/reporting/shipment_report.py", "shipment", "Shipment volume", ",", "internal_id"),
    ("services/billing/reporting/revenue_report.py", "revenue", "Revenue summary", ";", "tenant_id"),
    ("services/identity/reporting/access_report.py", "access", "Access audit", "|", "session_key"),
    ("services/orders/reporting/audit_report.py", "audit", "Order audit", "\\t", "batch_id"),
]

GO_TOOLS = [
    ("tools/cmd/import.go", "Import", "import", "manifest"),
    ("tools/cmd/export.go", "Export", "export", "snapshot"),
    ("tools/cmd/archive.go", "Archive", "archive", "backup"),
    ("tools/cmd/purge.go", "Purge", "purge", "stale"),
]

CS_JOBS = [
    ("jobs/IngestJob.cs", "Ingest", "ingested", "event", "bad event"),
    ("jobs/MaintenanceJob.cs", "Maintenance", "maintained", "task", "stale task"),
    ("jobs/NotifierJob.cs", "Notifier", "notified", "digest", "undeliverable"),
    ("jobs/ReconcilerJob.cs", "Reconciler", "reconciled", "ledger", "mismatch"),
]

# ----------------------------------------------------------------------
# Noise modules — each a deliberately distinct structural shape

NOISE_FILES = {
    "platform/errors.py": '''\
"""Shared exception hierarchy."""


class MeridianError(Exception):
    """Base error carrying a machine-readable code."""

    code = "meridian_error"

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {{}}


class NotFoundError(MeridianError):
    code = "not_found"


class ConflictError(MeridianError):
    code = "conflict"


class RateLimitedError(MeridianError):
    def __init__(self, retry_after):
        super().__init__("slow down")
        self.retry_after = retry_after
''',
    "platform/http/filters.py": '''\
"""Query-string filter parsing (single function, no classes)."""

ALLOWED_PATTERN = __import__("re").compile(r"^[a-z_]+$")


def parse_filters(query_params, allowed):
    """Turn ?status=x&channel=y into a dict restricted to `allowed`."""
    filters = {{}}
    for name in allowed:
        raw = query_params.get(name)
        if raw is None or raw == "":
            continue
        if not ALLOWED_PATTERN.match(name):
            continue
        values = [v for v in raw.split(",") if v]
        filters[name] = values[0] if len(values) == 1 else values
    return filters
''',
    "platform/db/pool.py": '''\
"""Async connection pool (async/await shape)."""

import asyncio
import contextlib


class Pool:
    def __init__(self, dsn, size=8):
        self._dsn = dsn
        self._semaphore = asyncio.Semaphore(size)
        self._connections = asyncio.Queue()
        self._size = 0

    async def acquire(self):
        await self._semaphore.acquire()
        try:
            return self._connections.get_nowait()
        except asyncio.QueueEmpty:
            self._size += 1
            return await self._connect()

    async def _connect(self):
        reader, writer = await asyncio.open_connection(*self._dsn.split(":"))
        return reader, writer

    @contextlib.asynccontextmanager
    async def transaction(self):
        conn = await self.acquire()
        try:
            yield _Cursor(conn)
        finally:
            await self._connections.put(conn)
            self._semaphore.release()


class _Cursor:
    def __init__(self, conn):
        self._conn = conn

    async def execute(self, statement, params=None):
        return None
''',
    "platform/config/loader.py": '''\
"""Environment-layered JSON config loader."""

import json
import os
from pathlib import Path


def load(path, env_prefix="MERIDIAN_"):
    settings = json.loads(Path(path).read_text())
    for key in list(settings):
        override = os.environ.get(env_prefix + key.upper())
        if override is not None:
            settings[key] = _coerce(override)
    return settings


def _coerce(text):
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text
''',
    "platform/logging/setup.py": '''\
"""Structured logging bootstrap with a rotating file handler."""

import logging
import logging.handlers
import sys

_CONFIGURED = False


def setup(level="INFO", logfile=None):
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger()
    root.setLevel(level.upper())
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(stream)
    if logfile:
        rotating = logging.handlers.RotatingFileHandler(
            logfile, maxBytes=10_000_000, backupCount=5
        )
        root.addHandler(rotating)
    _CONFIGURED = True
''',
    "platform/observability/metrics.py": '''\
"""Minimal registry of counters and gauges (dict-of-dicts shape)."""

import time

_METRICS = {}


def counter(name, labels=None):
    key = (name, tuple(sorted((labels or {}).items())))
    bucket = _METRICS.setdefault(key, {"kind": "counter", "value": 0, "updated": 0.0})
    return lambda amount=1: _bump(bucket, amount)


def gauge(name, labels=None):
    key = (name, tuple(sorted((labels or {}).items())))
    bucket = _METRICS.setdefault(key, {"kind": "gauge", "value": 0, "updated": 0.0})
    return lambda value: _set(bucket, value)


def _bump(bucket, amount):
    bucket["value"] += amount
    bucket["updated"] = time.time()


def _set(bucket, value):
    bucket["value"] = value
    bucket["updated"] = time.time()


def snapshot():
    return {
        f"{name}|{dict(labels)}": entry
        for (name, labels), entry in sorted(_METRICS.items())
    }
''',
    "platform/messaging/bus.py": '''\
"""In-process pub/sub bus driven by an asyncio queue."""

import asyncio


class Bus:
    def __init__(self):
        self._queue = asyncio.Queue()
        self._subscribers = {}

    def subscribe(self, topic, handler):
        self._subscribers.setdefault(topic, []).append(handler)

    async def publish(self, topic, payload):
        await self._queue.put((topic, payload))

    async def run(self):
        while True:
            topic, payload = await self._queue.get()
            for handler in self._subscribers.get(topic, []):
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            self._queue.task_done()
''',
    "platform/search/indexer.py": '''\
"""Batched inverted-index builder (generator pipeline shape)."""

from collections import defaultdict


def tokenize(text):
    return [t.strip(".,:;").lower() for t in text.split() if t.strip(".,:;")]


def batches(documents, size=100):
    batch = []
    for document in documents:
        batch.append(document)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def build_index(documents):
    index = defaultdict(set)
    for batch in batches(documents):
        for document in batch:
            doc_id = document["id"]
            for token in set(tokenize(document["body"])):
                index[token].add(doc_id)
    return dict(index)
''',
    "platform/storage/blob.py": '''\
"""Content-addressed blob store (protocol-style class)."""

import hashlib
import os
import tempfile


class BlobStore:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def put(self, data):
        digest = hashlib.sha256(data).hexdigest()
        bucket = os.path.join(self.root, digest[:2])
        os.makedirs(bucket, exist_ok=True)
        target = os.path.join(bucket, digest)
        if not os.path.exists(target):
            fd, temporary = tempfile.mkstemp(dir=bucket)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temporary, target)
        return digest

    def open(self, digest):
        return open(self._path(digest), "rb")

    def _path(self, digest):
        return os.path.join(self.root, digest[:2], digest)
''',
    "platform/websockets/hub.py": '''\
"""WebSocket fan-out hub (dict + set bookkeeping)."""

import asyncio
import json


class Hub:
    def __init__(self):
        self._clients = {}
        self._topics = {}
        self._lock = asyncio.Lock()

    async def register(self, client, topics):
        async with self._lock:
            self._clients[id(client)] = client
            for topic in topics:
                self._topics.setdefault(topic, set()).add(id(client))

    async def broadcast(self, topic, payload):
        message = json.dumps({"topic": topic, "payload": payload})
        async with self._lock:
            recipients = [
                self._clients[cid]
                for cid in self._topics.get(topic, set())
                if cid in self._clients
            ]
        for recipient in recipients:
            await recipient.send(message)

    async def disconnect(self, client):
        async with self._lock:
            self._clients.pop(id(client), None)
            for members in self._topics.values():
                members.discard(id(client))
''',
    "services/orders/domain/pricing.py": '''\
"""Pure pricing rules (small function set, no classes)."""

TIER_DISCOUNTS = {"starter": 0.0, "growth": 0.05, "scale": 0.12}


def line_total(unit_price, quantity, tier="starter"):
    gross = unit_price * quantity
    return round(gross * (1 - TIER_DISCOUNTS.get(tier, 0)), 2)


def order_total(lines, tier="starter"):
    subtotal = sum(line_total(**line, tier=tier) for line in lines)
    shipping = 0 if subtotal > 500 else 12.5
    tax = round(subtotal * 0.2, 2)
    return {"subtotal": subtotal, "shipping": shipping, "tax": tax, "total": subtotal + shipping + tax}
''',
    "services/billing/domain/tax.py": '''\
"""Tax jurisdiction resolution table (match/case shape)."""

JURISDICTIONS = {
    "DE": 0.19,
    "FR": 0.20,
    "UK": 0.20,
    "US-CA": 0.0725,
    "US-NY": 0.04,
}


def resolve_rate(country, region=None):
    if country == "US" and region:
        return JURISDICTIONS.get(f"US-{region}", 0.0)
    return JURISDICTIONS.get(country, 0.0)


def apply_tax(amount, country, region=None, exempt=False):
    if exempt:
        return {"amount": amount, "rate": 0.0, "tax": 0.0}
    rate = resolve_rate(country, region)
    tax = round(amount * rate, 2)
    return {"amount": amount, "rate": rate, "tax": tax, "total": amount + tax}
''',
    "services/identity/domain/tokens.py": '''\
"""JWT-ish encode/decode using hmac (two small functions)."""

import base64
import hashlib
import hmac
import json


def encode(claims, secret):
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode())
    body = base64.urlsafe_b64encode(json.dumps(claims).encode())
    signing_input = header + b"." + body
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + base64.urlsafe_b64encode(signature)).decode()


def decode(token, secret):
    header, body, signature = token.encode().split(b".")
    expected = hmac.new(secret.encode(), header + b"." + body, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, base64.urlsafe_b64encode(expected)):
        raise ValueError("bad signature")
    return json.loads(base64.urlsafe_b64decode(body))
''',
    "services/identity/api/middleware.py": '''\
"""Decorator-based auth middleware chain."""

from functools import wraps

from services.identity.domain import tokens


def require_scope(scope):
    def decorator(handler):
        @wraps(handler)
        def wrapper(request, *args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return {"error": "unauthorized"}, 401
            try:
                claims = tokens.decode(header[7:], request.app.secret)
            except ValueError:
                return {"error": "invalid token"}, 401
            if scope not in claims.get("scopes", []):
                return {"error": "forbidden"}, 403
            request.claims = claims
            return handler(request, *args, **kwargs)

        return wrapper

    return decorator
''',
    "services/billing/api/rate_limit.py": '''\
"""Token-bucket rate limiter (floating-point arithmetic shape)."""

import time


class TokenBucket:
    def __init__(self, rate, capacity):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.updated = time.monotonic()

    def allow(self, amount=1.0):
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True
''',
    "services/identity/api/passwords.py": '''\
"""Password hashing helpers (module functions over a C library)."""

import hashlib
import hmac
import os

ITERATIONS = 210_000


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    scheme, iterations, salt_hex, digest_hex = stored.split("$")
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
    )
    return hmac.compare_digest(candidate.hex(), digest_hex)
''',
    "services/orders/api/app.py": '''\
"""Application factory (closure registration shape)."""

from platform.config import loader
from platform.logging import setup as setup_logging


def create_app(config_path, **overrides):
    settings = loader.load(config_path)
    settings.update(overrides)
    setup_logging(level=settings.get("log_level", "INFO"))
    app = _App(settings)
    for module in _MODULES:
        module.register(app)
    return app


class _App:
    def __init__(self, settings):
        self.settings = settings
        self.routes = {}

    def route(self, path):
        def decorator(handler):
            self.routes[path] = handler
            return handler

        return decorator


_MODULES = []
''',
    "services/orders/jobs/consolidator.py": '''\
"""Batch consolidator using itertools grouping."""

import itertools
from collections import defaultdict


def consolidate(events, key="order_id", window=50):
    grouped = defaultdict(list)
    for event in events:
        grouped[event[key]].append(event)
    consolidated = []
    for identifier, batch in grouped.items():
        for chunk in _chunks(sorted(batch, key=lambda e: e["ts"]), window):
            consolidated.append(
                {
                    "key": identifier,
                    "count": len(chunk),
                    "first_ts": chunk[0]["ts"],
                    "last_ts": chunk[-1]["ts"],
                    "payloads": [c["payload"] for c in chunk],
                }
            )
    return consolidated


def _chunks(seq, size):
    iterator = iter(seq)
    while chunk := list(itertools.islice(iterator, size)):
        yield chunk
''',
    "tools/internal/fsutil/fsutil.go": '''\
package fsutil

import (
\t"os"
\t"path/filepath"
)

// SafeMove moves a file, creating the parent directory when needed.
func SafeMove(source, destination string) error {
\tif err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
\t\treturn err
\t}
\treturn os.Rename(source, destination)
}

// Exists reports whether the path is present.
func Exists(path string) bool {
\t_, err := os.Stat(path)
\treturn err == nil
}
''',
    "tools/internal/manifest/manifest.go": '''\
package manifest

import (
\t"encoding/json"
\t"os"
)

// Entry is one recorded artifact.
type Entry struct {
\tName   string `json:"name"`
\tSize   int64  `json:"size"`
\tSha256 string `json:"sha256"`
}

// Manifest is an ordered collection of entries.
type Manifest struct {
\tVersion int     `json:"version"`
\tEntries []Entry `json:"entries"`
}

// Load reads a manifest from disk.
func Load(path string) (*Manifest, error) {
\tdata, err := os.ReadFile(path)
\tif err != nil {
\t\treturn nil, err
\t}
\tmanifest := &Manifest{}
\tif err := json.Unmarshal(data, manifest); err != nil {
\t\treturn nil, err
\t}
\treturn manifest, nil
}

// Save writes the manifest back to disk.
func (m *Manifest) Save(path string) error {
\tdata, err := json.MarshalIndent(m, "", "  ")
\tif err != nil {
\t\treturn err
\t}
\treturn os.WriteFile(path, data, 0o644)
}
''',
    "jobs/JobRegistry.cs": '''\
using System;
using System.Collections.Generic;

namespace Meridian.Jobs
{
    public static class JobRegistry
    {
        private static readonly IDictionary<string, Func<IDictionary<string, string>, IJob>> Factories =
            new Dictionary<string, Func<IDictionary<string, string>, IJob>>();

        public static void Register(string name, Func<IDictionary<string, string>, IJob> factory)
        {
            Factories[name] = factory;
        }

        public static IJob Create(string name, IDictionary<string, string> configuration)
        {
            Func<IDictionary<string, string>, IJob> factory;
            if (!Factories.TryGetValue(name, out factory))
            {
                throw new KeyNotFoundException("unknown job: " + name);
            }
            return factory(configuration);
        }

        public static IEnumerable<string> Names()
        {
            return Factories.Keys;
        }
    }
}
''',
}

# Extra flavor files (not indexed; they exist for realism)
README = """\
# meridian

Growth-stage SaaS: orders, billing, and identity services, a Go toolchest,
and .NET background jobs. Three teams, one repo, four years of "temporary"
copy-paste. Proceed accordingly.
"""

COMPOSE = """\
services:
  orders:
    build: services/orders
  billing:
    build: services/billing
  identity:
    build: services/identity
  jobs:
    build: jobs
"""

INIT_PATHS = [
    "platform",
    "platform/db",
    "platform/http",
    "platform/config",
    "platform/logging",
    "platform/observability",
    "platform/messaging",
    "platform/search",
    "platform/storage",
    "platform/websockets",
    "services/orders",
    "services/orders/api",
    "services/orders/api/handlers",
    "services/orders/store",
    "services/orders/clients",
    "services/orders/caching",
    "services/orders/reporting",
    "services/orders/domain",
    "services/orders/jobs",
    "services/billing",
    "services/billing/api",
    "services/billing/api/handlers",
    "services/billing/store",
    "services/billing/clients",
    "services/billing/caching",
    "services/billing/reporting",
    "services/billing/domain",
    "services/identity",
    "services/identity/api",
    "services/identity/api/handlers",
    "services/identity/store",
    "services/identity/clients",
    "services/identity/caching",
    "services/identity/reporting",
    "services/identity/domain",
    "tools",
    "tools/cmd",
    "tools/internal",
    "tools/internal/fsutil",
    "tools/internal/manifest",
    "jobs",
]


def _handler_text(spec):
    path, cls, plural, key, extra, size_cap, allowed = spec
    return HANDLER.format(
        cls=cls,
        plural=plural,
        key=key,
        size_cap=size_cap,
        allowed="[" + ", ".join(f'"{a}"' for a in allowed) + "]",
        required='["' + key + '", "' + extra + '"]',
        missing=f"{plural[:-1]} not found",
        conflict=f"{plural[:-1]} already exists",
        created_log=f"created {plural[:-1]}",
        updated_log=f"updated {plural[:-1]}",
        deleted_log=f"deleted {plural[:-1]}",
        state_default="active",
    )


def _repository_text(spec):
    _, cls, plural, id_column = spec
    return REPOSITORY.format(cls=cls, plural=plural, table=plural, id_column=id_column)


def _client_text(spec):
    _, cls, service = spec
    return CLIENT.format(cls=cls, service=service)


def _cache_text(spec):
    _, cls, kind = spec
    return CACHE.format(cls=cls, kind=kind)


def _report_text(spec):
    _, fn, title, delim, skip = spec
    return REPORT.format(fn=fn, title=title, delim=delim, skip=skip)


def _subst(template: str, **mapping) -> str:
    """Placeholder substitution for templates with literal braces (Go, C#)."""
    text = template
    for key, value in mapping.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def _go_text(spec):
    _, title, name, pattern = spec
    return _subst(GO_TOOL, Title=title, name=name, pattern=pattern)


def _cs_text(spec):
    _, title, done, prefix, bad = spec
    return _subst(CS_JOB, Title=title, DoneLabel=done, ItemPrefix=prefix, BadItem=bad)


FAMILIES = [
    (
        "crud-handlers",
        [_handler_text(spec) for spec in HANDLERS],
        [spec[0] for spec in HANDLERS],
    ),
    (
        "sql-repositories",
        [_repository_text(spec) for spec in REPOSITORIES],
        [spec[0] for spec in REPOSITORIES],
    ),
    (
        "http-clients",
        [_client_text(spec) for spec in CLIENTS],
        [spec[0] for spec in CLIENTS],
    ),
    (
        "ttl-caches",
        [_cache_text(spec) for spec in CACHES],
        [spec[0] for spec in CACHES],
    ),
    (
        "table-reports",
        [_report_text(spec) for spec in REPORTS],
        [spec[0] for spec in REPORTS],
    ),
    (
        "go-commands",
        [_go_text(spec) for spec in GO_TOOLS],
        [spec[0] for spec in GO_TOOLS],
    ),
    (
        "cs-jobs",
        [_cs_text(spec) for spec in CS_JOBS],
        [spec[0] for spec in CS_JOBS],
    ),
]


def generate(dest: Path) -> dict:
    """Write the fixture tree; return ground truth + stats."""
    dest = Path(dest)
    for rel in INIT_PATHS:
        (dest / rel).mkdir(parents=True, exist_ok=True)
        (dest / rel / "__init__.py").write_text("")

    for family_id, texts, paths in FAMILIES:
        for text, rel in zip(texts, paths):
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_text(text)

    for rel, text in NOISE_FILES.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).write_text(text)

    (dest / "README.md").write_text(README)
    (dest / "docker-compose.yml").write_text(COMPOSE)

    indexed = [path for _, _, paths in FAMILIES for path in paths] + list(NOISE_FILES)
    lines = sum(
        (dest / rel).read_text().count("\n") for rel in indexed
    )
    return {
        "groups": [
            {"id": family_id, "files": paths, "min_similarity": 0.95}
            for family_id, _, paths in FAMILIES
        ],
        "negative_pairs": [],
        "stats": {"indexed_files": len(indexed), "approx_lines": lines},
    }


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "meridian")
    result = generate(target)
    (target.parent / f"{target.name}_ground_truth.json").write_text(
        json.dumps(result, indent=2)
    )
    print(json.dumps(result["stats"]))
