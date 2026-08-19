import argparse
import sys

from legacy_app.io.config_loader import load_config
from legacy_app.models import Invoice, Tenant


def build_parser():
    parser = argparse.ArgumentParser(description="Legacy billing CLI")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    tenant = Tenant(name=config["tenant"], region=config.get("region", "eu"))
    invoice = Invoice(tenant=tenant.name, amount=config.get("amount", 0))
    if args.dry_run:
        print(f"would issue {invoice.amount} for {tenant.name} in {tenant.region}")
        return 0
    print(f"issued {invoice.amount} for {tenant.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
