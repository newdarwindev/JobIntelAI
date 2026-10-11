# On-demand local environments

Run from the repository root with installed locked Python dependencies and Docker
Compose. The shared runner starts fresh PostgreSQL, explicitly runs Alembic, waits
for provider/API readiness and discovers Docker-assigned loopback ports. No public
preview or hosted provider is enabled. Fixture/emulator results are authored
contract evidence; only the explicitly selected local mode performs model inference.

```bash
# Complete zero-paid API/CLI contract, concurrent runs and cleanup checks.
python -m scripts.environment_smoke

# Bounded disposable session. The command receives JOBINTEL_ENVIRONMENT JSON
# containing base, project, mode, lease path and optional control_base.
python -m scripts.environment run --mode emulator --acquisition --lifetime 3600 -- python my_check.py

# Explicit persistent developer session; save the printed project/endpoint JSON.
python -m scripts.environment up --persistent --mode fixture --acquisition
python -m scripts.environment status --project <printed-project>
python -m scripts.environment stop --project <printed-project>
python -m scripts.environment start --project <printed-project>
python -m scripts.environment reset --project <printed-project>
```

`run` always cleans its newly owned containers, networks and data/output volumes
on success, failure, SIGINT, SIGTERM or command timeout. Lifetime is 30–7200 seconds,
including provisioning. A detached watchdog removes expired resources even after
the launcher is killed with SIGKILL. Commands run in separate process groups so
interruption also terminates their descendants. Resource deletion requires both
the recorded unique ownership label and the Compose project label; choosing a
similar name cannot delete an existing developer stack. Status and stop are
idempotent; unknown projects are reported as unmanaged and remain untouched.
An already existing project cannot be claimed. A persistent session can be resumed
only if every resource belongs to its recorded owner.

`up` requires `--persistent`. Persistent stop preserves database/output volumes;
start retains their data and rediscovers endpoints. Explicit reset removes only
that session's owned volumes. Legacy named `scripts/runtime.py` sessions are
independent and remain usable. Persistent sessions have no expiry watchdog.
Developer inputs remain private; authored smoke inputs and disposable credentials
are separate from inherited application database/provider settings.

Origins, scoped TLS trust and the pinning proxy are started only with
`--acquisition`. Fixture mode starts no emulator/model; emulator mode adds only
the Responses service; `--mode local` adds the licensed checksum-pinned CPU engine.
Weights/license persist in `local_data/models` and are never deleted by teardown.
The local profile limits the engine to 2 CPUs, 5 GiB, an 8192-token context, one
slot and 2048 output tokens, with no host inference port. CI uses the same cache
and publishes measured model errors separately from service pass counts.
`--offline` requires prepared wheels and verified weights; `--ca-bundle` mounts a
combined trusted bundle for build/runtime HTTPS. TLS verification stays enabled.

Ownership records live at `work/environments/<project>/lease.json`. They contain
source/config provenance, endpoints, bounded lifetime, outcome and sanitized
container status/exit/health and protocol diagnostics. Startup failures retain
partial service evidence; individual unavailable collectors cannot prevent cleanup.
Generated certificates/keys live in ignored `local_data/environments/<project>`;
owned disposable trust is removed after teardown, while persistent trust survives
stop. Full process environments, Compose-rendered secret values, arbitrary logs,
private input bodies and TLS keys are excluded from diagnostic artifacts.

```bash
# Recover expired disposable runs from this checkout's ownership registry.
python -m scripts.environment_lifecycle reap
# CI finalizer: remove all recorded disposable runs from this isolated checkout.
python -m scripts.environment_lifecycle reap --all-disposable
```

Cleanup never prunes Docker globally or deletes shared model assets. Dependencies
are stopped in order: APIs first, then their origin/proxy owners. Browser UI09–UI11,
controlled acquisition and Responses checks, and the CPU smoke use this lifecycle.
Every Actions outcome uploads per-run diagnostics plus the driver's exact counts;
full browser reports retain all attempts/traces/videos and only successful attempts
enter README recordings. PR/fork permissions are read-only. Remote private preview
is not implemented or needed for this loopback contract.

Network B/C measurement failures retain their last atomic checkpoint and actual
counted request hashes in driver evidence. Uncertain predictions/usage remain
unknown, and failed or unverified rescoring never counts as a passed service case.
