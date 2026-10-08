"""In-memory fakes standing in for the Supabase client during tests."""

import uuid
from datetime import datetime, timezone


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, table: "FakeTable", op: str, payload=None):
        self._table = table
        self._op = op
        self._payload = payload
        self._filters = []
        self._order_by = None

    def gte(self, column, value):
        self._filters.append(("gte", column, value))
        return self

    def eq(self, column, value):
        self._filters.append(("eq", column, value))
        return self

    def order(self, column, desc=False):
        self._order_by = (column, desc)
        return self

    def execute(self):
        if self._op == "insert":
            rows = self._payload if isinstance(self._payload, list) else [self._payload]
            for row in rows:
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            self._table.rows.extend(rows)
            return FakeResult(rows)

        if self._op == "update":
            for row in self._table.rows:
                if all(row.get(col) == val for _, col, val in self._filters):
                    row.update(self._payload)
            return FakeResult(self._table.rows)

        if self._op == "upsert":
            key_col = self._payload.get("_on_conflict", "id")
            payload = {k: v for k, v in self._payload.items() if k != "_on_conflict"}
            for row in self._table.rows:
                if row.get(key_col) == payload.get(key_col):
                    row.update(payload)
                    return FakeResult([row])
            self._table.rows.append(payload)
            return FakeResult([payload])

        rows = list(self._table.rows)
        for _, col, val in self._filters:
            rows = [r for r in rows if r.get(col) is not None and str(r.get(col)) >= str(val)]
        if self._order_by:
            col, desc = self._order_by
            rows = sorted(rows, key=lambda r: r.get(col), reverse=desc)
        return FakeResult(rows)


class FakeTable:
    def __init__(self):
        self.rows: list[dict] = []

    def insert(self, payload):
        return FakeQuery(self, "insert", payload)

    def select(self, *_args):
        return FakeQuery(self, "select")

    def update(self, payload):
        return FakeQuery(self, "update", payload)

    def upsert(self, payload, on_conflict=None):
        merged = dict(payload)
        merged["_on_conflict"] = on_conflict or "id"
        return FakeQuery(self, "upsert", merged)


class FakeSupabaseClient:
    def __init__(self):
        self._tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self._tables.setdefault(name, FakeTable())
