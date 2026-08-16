from app.news.jobs import run_news_sentiment


def main() -> None:
    count = run_news_sentiment()
    print(f"Scored {count} currencies")


if __name__ == "__main__":
    main()
