"""Local runtime checks. No network requests or provider generation probes."""
import os
import sqlite3
import tempfile


def storage_ready(planning, settings):
    directories = [planning.store.root]
    if settings.enabled:
        directories.append(settings.usage_root)
    try:
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=directory) as probe:
                probe.write(b'readiness')
                probe.flush()
                os.fsync(probe.fileno())
        ledger = settings.usage_root/'a0-usage.sqlite3'
        if settings.enabled and ledger.exists():
            with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True, timeout=3) as db:
                if db.execute('PRAGMA quick_check(1)').fetchone()[0] != 'ok':
                    return False
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='calls'").fetchone():
                    db.execute('SELECT status,reserved,actual,usage FROM calls LIMIT 0')
        return True
    except (OSError, sqlite3.Error):
        return False


def local_checks(planning, settings):
    return dict(planning=planning.ready, storage=storage_ready(planning, settings),
        model_credentials=not settings.enabled or bool(settings.api_key))
