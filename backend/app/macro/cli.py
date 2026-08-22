from app.macro.jobs import (
    run_cpi_ingestion,
    run_current_account_ingestion,
    run_gdp_ingestion,
    run_macro_ingestion,
)


def main() -> None:
    count = run_macro_ingestion()
    print(f"Upserted {count} macro rate rows")
    cpi_count = run_cpi_ingestion()
    print(f"Upserted {cpi_count} macro CPI rows")
    gdp_count = run_gdp_ingestion()
    print(f"Upserted {gdp_count} macro GDP rows")
    ca_count = run_current_account_ingestion()
    print(f"Upserted {ca_count} macro current account rows")


if __name__ == "__main__":
    main()
