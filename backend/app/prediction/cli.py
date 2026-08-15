import argparse

from app.prediction.jobs import run_backtest_job, run_forecast


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ForexCast prediction engine")
    parser.add_argument("--mode", choices=["forecast", "backtest"], required=True)
    args = parser.parse_args(argv)

    if args.mode == "forecast":
        count = run_forecast()
    else:
        count = run_backtest_job()

    print(f"Wrote {count} rows ({args.mode})")


if __name__ == "__main__":
    main()
