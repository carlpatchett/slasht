from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Tenant:
    name: str
    region: str = "eu"


@dataclass
class Invoice:
    tenant: str
    amount: int
    created_at: datetime = field(default_factory=datetime.utcnow)
    lines: list[str] = field(default_factory=list)

    def total(self):
        return self.amount + sum(len(line) for line in self.lines)
