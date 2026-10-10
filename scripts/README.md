# scripts/

## fake_worker.py

Stands in for a real worker when testing the backend's worker protocol (API.md section 9). Registers with a pairing code, heartbeats, polls for jobs, and posts canned logs and results from `shared/examples/worker/<job type>.json`.

Requires `requests` (standard library otherwise).

```bash
BACKEND_URL=http://localhost:8000 PAIRING_CODE=ABCD-1234 python scripts/fake_worker.py
```

To exercise the Debugger's failure-handling path, force every Nth job to fail:

```bash
BACKEND_URL=http://localhost:8000 PAIRING_CODE=ABCD-1234 python scripts/fake_worker.py --fail-every 3
```

Stop with Ctrl-C. The worker token is kept in memory only and is never printed.
