import argparse

from app.ingestion.rates import run_backfill, run_daily


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ForexCast rate ingestion")
    parser.add_argument("--mode", choices=["daily", "backfill"], required=True)
    parser.add_argument("--start-date", default="1999-01-04")
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args(argv)

    if args.mode == "daily":
        count = run_daily()
    else:
        count = run_backfill(start_date=args.start_date, end_date=args.end_date)

    print(f"Upserted {count} rate rows ({args.mode})")


if __name__ == "__main__":
    main()
