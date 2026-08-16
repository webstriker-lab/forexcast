from app.macro.jobs import run_macro_ingestion


def main() -> None:
    count = run_macro_ingestion()
    print(f"Upserted {count} macro rate rows")


if __name__ == "__main__":
    main()
