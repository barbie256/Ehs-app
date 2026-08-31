"""Read-only structural comparison for the dedicated EHS test and development databases."""

from sqlalchemy import Engine, create_engine, inspect, text

from app.db.session import validate_development_url, validate_test_url
from tests.conftest import private_urls


def schema_snapshot(engine: Engine) -> dict[str, object]:
    inspector = inspect(engine)
    result: dict[str, object] = {}
    for table in sorted(name for name in inspector.get_table_names() if name != "alembic_version"):
        columns = tuple(
            (item["name"], str(item["type"]), item["nullable"], str(item.get("default")))
            for item in inspector.get_columns(table)
        )
        primary = inspector.get_pk_constraint(table)
        foreign_keys = tuple(
            sorted(
                (
                    item.get("name"),
                    tuple(item.get("constrained_columns") or ()),
                    item.get("referred_table"),
                    tuple(item.get("referred_columns") or ()),
                    tuple(sorted((item.get("options") or {}).items())),
                )
                for item in inspector.get_foreign_keys(table)
            )
        )
        unique_constraints = tuple(
            sorted(
                (item.get("name"), tuple(item.get("column_names") or ()))
                for item in inspector.get_unique_constraints(table)
            )
        )
        checks = tuple(
            sorted(
                (item.get("name"), " ".join(str(item.get("sqltext")).split()))
                for item in inspector.get_check_constraints(table)
            )
        )
        indexes = tuple(
            sorted(
                (
                    item.get("name"),
                    tuple(item.get("column_names") or ()),
                    item.get("unique"),
                    str(item.get("dialect_options")),
                )
                for item in inspector.get_indexes(table)
            )
        )
        result[table] = (
            columns,
            (primary.get("name"), tuple(primary.get("constrained_columns") or ())),
            foreign_keys,
            unique_constraints,
            checks,
            indexes,
        )
    return result


def current_head(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def main() -> None:
    development_url, test_url = private_urls()
    validate_development_url(development_url)
    validate_test_url(test_url, development_url=development_url)
    development = create_engine(development_url)
    test = create_engine(test_url)
    try:
        development_schema = schema_snapshot(development)
        test_schema = schema_snapshot(test)
        differing = sorted(
            name
            for name in development_schema.keys() | test_schema.keys()
            if development_schema.get(name) != test_schema.get(name)
        )
        print(
            f"development_head={current_head(development)} test_head={current_head(test)} "
            f"tables={len(test_schema)} structural_equivalence={not differing}"
        )
        if differing:
            print(f"differing_tables={','.join(differing)}")
            raise SystemExit(1)
    finally:
        development.dispose()
        test.dispose()


if __name__ == "__main__":
    main()
