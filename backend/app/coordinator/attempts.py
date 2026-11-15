"""Durable request outcomes with process-safe locking and explicit retry versions.

No automatic re-execution: identical completed requests replay their response;
known rejections need an explicit matching retry header. Abandoned work remains
unknown. A per-key SQLite exclusive transaction releases on worker exit and
works across processes without tying the API to POSIX-only locking modules.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import logging
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Literal

from pydantic import Field, model_validator
from app.api.errors import ApiProblem
from app.contracts.api import ContractModel, ErrorBody
from app.contracts.attempts import REQUEST_ID_PATTERN, RequestAttemptStatus
from app.planning.store import sync_dir

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 128*1024*1024  # bounded, while allowing native-resolution route polylines


def now():
    return datetime.now(timezone.utc)


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def save_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.attempt-',delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data,stream,allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
        sync_dir(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Failure(ContractModel):
    http_status: int = Field(ge=400,le=599)
    code: str
    message: str
    retry_safe: bool = False
    details: list[dict[str, str]] | None = None
    retry_not_before: datetime | None = None


class Record(ContractModel):
    schema_version: Literal[1] = 1
    payload_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    state: Literal['running','succeeded','failed','unknown']
    attempt: int = Field(ge=1)
    updated_at: datetime
    failure: Failure | None = None

    @model_validator(mode='after')
    def consistent_outcome(self):
        if (self.state in ('failed','unknown')) != (self.failure is not None):
            raise ValueError('Failure state and details disagree')
        if self.state=='unknown' and self.failure.retry_safe:
            raise ValueError('Unknown work cannot be retried')
        return self


class AttemptStore:
    def __init__(self, root, kind):
        self.root = Path(root)
        self.kind = kind

    def code(self, suffix):
        return self.kind.upper()+'_'+suffix

    def paths(self, key):
        if not re.fullmatch(REQUEST_ID_PATTERN,key):
            raise ApiProblem(422,'VALIDATION_ERROR','The request identifier is malformed.')
        return self.root/(key+'.json'),self.root/(key+'.response'),self.root/(key+'.lock')

    @contextmanager
    def lock(self, path):
        if path.is_symlink():
            raise ApiProblem(500,'REQUEST_RECORD_INVALID','The request lock is invalid.')
        # One database per key: an active model call never holds a global lock
        # against unrelated requests. No application data is stored in it.
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            connection = sqlite3.connect(path,timeout=0,isolation_level=None)
        except (OSError, sqlite3.Error):
            raise ApiProblem(503,'REQUEST_STORAGE_UNAVAILABLE','Durable request storage is unavailable; no new work was started.') from None
        try:
            try:
                connection.execute('BEGIN EXCLUSIVE')
            except sqlite3.OperationalError as error:
                if 'locked' not in str(error).lower() and 'busy' not in str(error).lower():
                    raise ApiProblem(503,'REQUEST_LOCK_UNAVAILABLE','The request lock is unavailable.') from None
                yield False
            else:
                yield True
        finally:
            connection.close()

    def read(self, path):
        if not path.exists():
            return None
        try:
            if path.is_symlink() or path.stat().st_size > 65536:
                raise ValueError('Invalid record')
            record = Record.model_validate_json(path.read_text())
            if record.updated_at.utcoffset() != timedelta(0):
                raise ValueError('UTC required')
            if record.failure and record.failure.retry_not_before and record.failure.retry_not_before.utcoffset() != timedelta(0):
                raise ValueError('UTC required')
            return record
        except (OSError,ValueError):
            raise ApiProblem(500,'REQUEST_RECORD_INVALID','A stored request record failed validation.') from None

    def cached(self, path, parse, expected_hash):
        if not path.is_file():
            return None
        try:
            if path.is_symlink() or path.stat().st_size > MAX_RESPONSE_BYTES:
                raise ValueError('Invalid response')
            return parse(json.loads(path.read_text()),expected_hash)
        except (OSError,ValueError,ApiProblem):
            raise ApiProblem(500,'REQUEST_RECORD_INVALID','A stored request response failed validation.') from None

    def view(self, key, record, *, state=None):
        failure = record.failure
        delay = max(0,math.ceil((failure.retry_not_before-now()).total_seconds())) if failure and failure.retry_not_before else 0
        state = state or record.state
        return RequestAttemptStatus(request_id=key,state=state,attempt=record.attempt,
            retry_allowed=bool(state=='failed' and failure and failure.retry_safe and delay==0),
            retry_after_seconds=delay,error=ErrorBody(code=failure.code,message=failure.message,details=failure.details) if failure else None,
            updated_at=record.updated_at)

    def unknown(self, record):
        return record.model_copy(update=dict(state='unknown',updated_at=now(),failure=Failure(http_status=409,
            code=self.code('OUTCOME_UNKNOWN'),message='The previous worker ended without a durable response. Do not automatically submit another model request.')))

    def failed_error(self, key, record):
        status = self.view(key,record)
        failure = record.failure
        return ApiProblem(failure.http_status,failure.code,failure.message,details=[*(failure.details or []),dict(
            type='request_attempt',state=status.state,request_id=key,attempt=str(status.attempt),
            retry_allowed=str(status.retry_allowed).lower(),retry_after_seconds=str(status.retry_after_seconds),
            retry_header='X-A-Stellar-Retry-Attempt')], retry_after_seconds=status.retry_after_seconds or None)

    def status(self, key, parse, *, response_path=None, legacy_claim=None):
        path,response,lock = self.paths(key)
        response = response_path or response
        record = self.read(path)
        if self.cached(response,parse,record.payload_hash if record else None) is not None:
            return RequestAttemptStatus(request_id=key,state='succeeded',attempt=record.attempt if record else 1,
                retry_allowed=False,retry_after_seconds=0,updated_at=record.updated_at if record else None)
        if record is None:
            if legacy_claim and legacy_claim.exists():
                return RequestAttemptStatus(request_id=key,state='unknown',attempt=1,retry_allowed=False,retry_after_seconds=0,
                    error=ErrorBody(code=self.code('OUTCOME_UNKNOWN'),message='This legacy claim has no recoverable outcome; it will not be replayed automatically.'))
            raise ApiProblem(404,self.code('ATTEMPT_NOT_FOUND'),'No stored request exists for this identifier.')
        with self.lock(lock) as acquired:
            record = self.read(path)
            if not acquired:
                return self.view(key,record,state='running')
            if record.state=='running':
                record = self.unknown(record)
                save_json(path,record.model_dump(mode='json'))
            if record.state=='succeeded':
                raise ApiProblem(500,'REQUEST_RECORD_INVALID','The completed request response is missing.')
            return self.view(key,record)

    def execute(self, key, payload, operation, parse, *, retry_attempt=None, response_path=None, legacy_claim=None):
        path,response,lock = self.paths(key)
        response = response_path or response
        expected = payload_hash(payload)
        with self.lock(lock) as acquired:
            record = self.read(path)
            if record and record.payload_hash != expected:
                raise ApiProblem(409,self.code('REQUEST_CONFLICT'),'This request ID was already used with different input.')
            if not acquired:
                raise ApiProblem(409,self.code('MESSAGE_IN_PROGRESS') if self.kind=='chat' else self.code('REQUEST_IN_PROGRESS'),
                    'This request is still running. Read its status instead of sending another model request.')
            result = self.cached(response,parse,expected)
            if result is not None:
                return result
            if legacy_claim and legacy_claim.exists() and record is None:
                raise ApiProblem(409,self.code('OUTCOME_UNKNOWN'),'This legacy request has no recoverable outcome; automatic replay is blocked.')
            if record and record.state=='running':
                record = self.unknown(record)
                save_json(path,record.model_dump(mode='json'))
            if record:
                if record.state=='succeeded':
                    raise ApiProblem(500,'REQUEST_RECORD_INVALID','The completed request response is missing.')
                if retry_attempt is None:
                    raise self.failed_error(key,record)
                if record.state!='failed' or not record.failure or not record.failure.retry_safe:
                    raise ApiProblem(409,self.code('RETRY_UNSAFE'),'The prior outcome cannot safely be retried under this request ID.')
                if retry_attempt != record.attempt:
                    raise ApiProblem(409,self.code('RETRY_CONFLICT'),'The retry version is stale. Read the current request status first.')
                delay = self.view(key,record).retry_after_seconds
                if delay:
                    raise ApiProblem(429,self.code('RETRY_DELAY'),'Wait for Retry-After before explicitly retrying.',
                        details=[dict(type='request_attempt',retry_after_seconds=str(delay))],retry_after_seconds=delay)
            elif retry_attempt is not None:
                raise ApiProblem(409,self.code('RETRY_CONFLICT'),'An explicit retry requires an existing failed attempt.')
            record = Record(payload_hash=expected,state='running',attempt=record.attempt+1 if record else 1,updated_at=now())
            save_json(path,record.model_dump(mode='json'))
            try:
                result = operation()
                save_json(response,result.model_dump(mode='json'))
            except ApiProblem as error:
                delay = error.retry_after_seconds
                failure = Failure(http_status=error.status,code=error.code,message=error.message,details=error.details,retry_safe=error.retry_safe and not error.outcome_unknown,
                    retry_not_before=now()+timedelta(seconds=delay) if delay is not None else None)
                record = record.model_copy(update=dict(state='unknown' if error.outcome_unknown else 'failed',updated_at=now(),failure=failure))
                save_json(path,record.model_dump(mode='json'))
                raise self.failed_error(key,record) from None
            except Exception as error:
                logger.error('Unhandled %s request failure: %s', self.kind, type(error).__name__)
                record = record.model_copy(update=dict(state='unknown',updated_at=now(),failure=Failure(
                    http_status=500,code='INTERNAL_ERROR',
                    message='An unexpected backend error occurred. The request outcome is uncertain; do not automatically retry.')))
                save_json(path,record.model_dump(mode='json'))
                raise self.failed_error(key,record) from None
            # A published response remains authoritative if this final status
            # update is interrupted; the next lookup replays the response.
            record = record.model_copy(update=dict(state='succeeded',updated_at=now()))
            save_json(path,record.model_dump(mode='json'))
            return result
