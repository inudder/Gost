from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        panel_host TEXT NOT NULL DEFAULT '127.0.0.1',
        panel_port INTEGER NOT NULL DEFAULT 17777,
        gost_api_url TEXT,
        gost_api_username TEXT,
        gost_api_password TEXT,
        test_endpoint TEXT NOT NULL DEFAULT 'http://httpbin.org/status/204',
        egress_ip_endpoint TEXT NOT NULL DEFAULT 'http://api.ipify.org',
        default_timeout_ms INTEGER NOT NULL DEFAULT 6000,
        polling_interval_sec INTEGER NOT NULL DEFAULT 120,
        max_concurrent_checks INTEGER NOT NULL DEFAULT 10,
        degrade_latency_ms INTEGER NOT NULL DEFAULT 1500,
        last_global_check_started_at TEXT,
        last_global_check_finished_at TEXT,
        last_gost_poll_at TEXT,
        last_gost_error TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    INSERT OR IGNORE INTO settings (id) VALUES (1);

    CREATE TABLE IF NOT EXISTS nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        protocol TEXT NOT NULL DEFAULT 'socks5',
        host TEXT NOT NULL,
        port INTEGER NOT NULL,
        username TEXT,
        password TEXT,
        source_type TEXT NOT NULL DEFAULT 'manual',
        source_ref TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        tags TEXT,
        test_url_override TEXT,
        timeout_override_ms INTEGER,
        current_status TEXT NOT NULL DEFAULT 'unknown',
        last_check_started_at TEXT,
        last_check_finished_at TEXT,
        last_latency_ms INTEGER,
        last_egress_ip TEXT,
        last_error_code TEXT,
        last_error_message TEXT,
        last_failed_stage TEXT,
        last_success_at TEXT,
        fail_streak INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_type, source_ref)
    );

    CREATE INDEX IF NOT EXISTS ix_nodes_enabled ON nodes(enabled);
    CREATE INDEX IF NOT EXISTS ix_nodes_source ON nodes(source_type, source_ref);
    CREATE INDEX IF NOT EXISTS ix_nodes_status ON nodes(current_status);

    CREATE TABLE IF NOT EXISTS checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL DEFAULT 'unknown',
        failed_stage TEXT,
        latency_ms INTEGER,
        egress_ip TEXT,
        error_code TEXT,
        error_message TEXT,
        raw_result_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(node_id) REFERENCES nodes(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS ix_checks_node_started ON checks(node_id, started_at DESC);
    CREATE INDEX IF NOT EXISTS ix_checks_status ON checks(status);

    CREATE TABLE IF NOT EXISTS gost_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_name TEXT NOT NULL UNIQUE,
        address TEXT,
        protocol TEXT,
        state TEXT,
        last_seen_at TEXT,
        error_note TEXT,
        raw_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_gost_services_state ON gost_services(state);
    """,
}


async def run_migrations(engine: AsyncEngine) -> None:
    database_path = Path(engine.url.database or "")
    if database_path:
        database_path.parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        rows = await connection.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
        applied_versions = {row[0] for row in rows}

        for version in sorted(MIGRATIONS):
            if version in applied_versions:
                continue
            statements = [statement.strip() for statement in MIGRATIONS[version].split(";") if statement.strip()]
            for statement in statements:
                await connection.execute(text(statement))
            await connection.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                {"version": version},
            )
