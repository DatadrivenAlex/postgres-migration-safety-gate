from migration_guard.analyzer import analyze


def ids(sql: str) -> set[str]:
    return {finding.rule_id for finding in analyze(sql).findings}


def test_destructive_and_rolling_deploy_checks():
    report = analyze("ALTER TABLE users DROP COLUMN email;")
    assert report.blocked
    assert {"PG001", "PG002"} <= ids("ALTER TABLE users DROP COLUMN email;")
    assert any("rolling deploy" in item.message for item in report.findings)


def test_not_null_without_default_and_type_change_warn():
    found = ids(
        "ALTER TABLE orders ADD COLUMN code TEXT NOT NULL; ALTER TABLE orders ALTER COLUMN amount TYPE BIGINT;"
    )
    assert {"PG003", "PG004"} <= found


def test_concurrent_index_requires_nontransactional_migration():
    assert "PG006" in ids("BEGIN; CREATE INDEX CONCURRENTLY ix ON t (id); COMMIT;")
    assert "PG006" not in ids("CREATE INDEX CONCURRENTLY ix ON t (id);")
    assert "PG005" in ids("CREATE INDEX ix ON t (id);")


def test_constraint_and_index_lock_hints():
    found = ids("ALTER TABLE t ADD CONSTRAINT fk FOREIGN KEY (x) REFERENCES p(id); DROP INDEX ix;")
    assert {"PG007", "PG008"} <= found
    assert "PG007" not in ids("ALTER TABLE t ADD CONSTRAINT ck CHECK (x > 0) NOT VALID;")


def test_rename_and_not_null_checks():
    assert {"PG009", "PG010"} <= ids(
        "ALTER TABLE t RENAME COLUMN old TO new; ALTER TABLE t ALTER COLUMN x SET NOT NULL;"
    )


def test_clean_additive_migration_has_no_findings():
    report = analyze("CREATE TABLE demo (id BIGINT PRIMARY KEY, label TEXT);")
    assert report.parsed_statements == 1
    assert report.findings == ()
    assert not report.blocked


def test_syntax_error_is_reported():
    report = analyze("ALTER TABLE ???")
    assert report.blocked
    assert report.findings[0].rule_id == "PG000"


def test_api_health_and_analysis():
    from fastapi.testclient import TestClient

    from migration_guard.api import app

    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    response = client.post("/analyze", json={"sql": "DROP TABLE users;"})
    assert response.status_code == 200
    assert response.json()["blocked"] is True
