"""HTTP delivery may fail after commit; the saved operation remains authoritative."""

import json

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from jobintel import mutation_operations as operations


class MutationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        key = request.headers.get("Idempotency-Key")
        if key is None or not operations.tracked_path(request.method, request.url.path):
            return await call_next(request)
        try:
            return await self.handle(request, call_next, operations.operation_id(key))
        except HTTPException as error:
            return JSONResponse({"detail": error.detail}, status_code=error.status_code)
        except SQLAlchemyError:
            return JSONResponse(
                {"detail": "Operation status unavailable. Preserve its identity before retrying."},
                status_code=503,
            )

    async def handle(self, request, call_next, key):
        factory = request.app.state.session_factory
        digest = operations.request_hash(request.method, request.url.path, await request.body())
        prior = await run_in_threadpool(
            operations.reserve, factory, key, request.method, request.url.path, digest
        )
        if prior:
            return operations.replay(prior)
        request.state.operation_id = key
        try:
            response = await call_next(request)
        except Exception:
            return operations.replay(await run_in_threadpool(operations.lookup, factory, key))
        record = await run_in_threadpool(operations.lookup, factory, key)
        rejected = getattr(request.state, "operation_rejected", False)
        if record["state"] == "uncertain" and (response.status_code < 500 or rejected):
            body = b"".join([part async for part in response.body_iterator])
            record = await run_in_threadpool(
                operations.reject,
                factory,
                key,
                {"status": response.status_code, "body": json.loads(body)},
                int(getattr(request.state, "operation_started", False)),
            )
        if record["state"] != "uncertain":
            return operations.replay(record)
        response.headers["X-Operation-ID"] = key
        response.headers["X-Operation-State"] = "uncertain"
        response.headers["Cache-Control"] = "no-store"
        return response
