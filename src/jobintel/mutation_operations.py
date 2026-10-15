"""Reserve once; save the response in the domain transaction; never rerun an unknown outcome."""

import json
import re
from functools import wraps
from hashlib import sha256
from inspect import signature
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import IntegrityError

from jobintel import db

MUTATIONS = re.compile(r"/jobs/[^/]+/(snapshots|fetch|extract|match)\Z")


def tracked_path(method, path):
    return method == "POST" and (
        path in {"/jobs/import", "/candidates/import", "/evaluate"}
        or MUTATIONS.fullmatch(path) is not None
    )


def operation_id(value):
    try:
        return UUID(value).hex
    except (ValueError, AttributeError) as error:
        raise HTTPException(422, "operation identity must be a UUID") from error


def request_hash(method, path, body):
    try:
        normalized = json.dumps(
            json.loads(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    except (ValueError, UnicodeError):
        normalized = body
    return sha256(method.encode() + b"\0" + path.encode() + b"\0" + normalized).hexdigest()


def output(row, key):
    if row is None:
        return {"operation_id": key, "state": "not_received", "execution_count": 0}
    return {
        "operation_id": row.id,
        "state": row.state,
        "method": row.method,
        "path": row.path,
        "created_at": row.created_at,
        "completed_at": row.completed_at,
        "http_status": row.http_status,
        "result": row.result,
        "execution_count": row.execution_count,
    }


def lookup(factory, key):
    with factory() as session:
        return output(session.get(db.MutationOperation, key), key)


def existing(factory, key, digest):
    with factory() as session:
        row = session.get(db.MutationOperation, key)
        if row is None:
            return None
        if row.request_sha256 is not None and row.request_sha256 != digest:
            raise HTTPException(409, "operation identity belongs to a different request")
        return output(row, key)


def reserve(factory, key, method, path, digest):
    found = existing(factory, key, digest)
    if found:
        return found
    try:
        with factory.begin() as session:
            session.add(
                db.MutationOperation(
                    id=key,
                    request_sha256=digest,
                    method=method,
                    path=path,
                    state="uncertain",
                )
            )
    except IntegrityError:
        return existing(factory, key, digest)
    return None


def finish(session, key, response, execution_count):
    row = session.get(db.MutationOperation, key)
    if row.state != "uncertain":
        return
    row.http_status, row.result = response["status"], response["body"]
    row.state = (
        "committed" if row.http_status < 400 or row.result.get("evaluation_run_id") else "rejected"
    )
    row.completed_at = db.now()
    row.execution_count = execution_count
    session.flush()


def reject(factory, key, response, execution_count):
    with factory.begin() as session:
        finish(session, key, response, execution_count)
    return lookup(factory, key)


def cancel_unsent(factory, key):
    rejection = {"detail": "Unsent operation cancelled. Start new work with a new identity."}
    try:
        with factory.begin() as session:
            row = session.get(db.MutationOperation, key)
            if row is not None:
                return output(row, key)
            timestamp = db.now()
            row = db.MutationOperation(
                id=key,
                state="rejected",
                created_at=timestamp,
                completed_at=timestamp,
                http_status=409,
                result=rejection,
                execution_count=0,
            )
            session.add(row)
            session.flush()
            return output(row, key)
    except IntegrityError:
        return lookup(factory, key)


def replay(record):
    headers = {"Cache-Control": "no-store", "X-Operation-ID": record["operation_id"]}
    headers["X-Operation-State"] = record["state"]
    if record["state"] == "uncertain":
        return JSONResponse(
            {"detail": "Operation outcome is uncertain. Check saved outcome before new work."},
            status_code=409,
            headers=headers,
        )
    return JSONResponse(record["result"], status_code=record["http_status"], headers=headers)


def tracked_mutation(function):
    parameters = signature(function)

    @wraps(function)
    def wrapped(*args, **kwargs):
        request = parameters.bind(*args, **kwargs).arguments["request"]
        if not getattr(request.state, "operation_id", None):
            return function(*args, **kwargs)
        request.state.operation_started = True
        result = function(*args, **kwargs)
        if isinstance(result, Response):
            body, status = json.loads(result.body), result.status_code
        else:
            body = jsonable_encoder(result)
            status = request.scope["route"].status_code or 200
        request.state.operation_response = {"status": status, "body": body}
        return result

    return wrapped
