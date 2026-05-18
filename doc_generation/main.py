from doc_generation.logging_config import configure_logging


def main() -> None:
    configure_logging()
    print("doc_generation is ready.")


if __name__ == "__main__":
    main()
