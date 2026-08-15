import argparse

from app.recommendations.jobs import run_alert_evaluation, run_recommendations


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ForexCast recommendation engine")
    parser.add_argument("--mode", choices=["recommendations", "alerts"], required=True)
    args = parser.parse_args(argv)

    if args.mode == "recommendations":
        count = run_recommendations()
        print(f"Wrote {count} rows (recommendations)")
    else:
        count = run_alert_evaluation()
        print(f"Fired {count} alerts (alerts)")


if __name__ == "__main__":
    main()
