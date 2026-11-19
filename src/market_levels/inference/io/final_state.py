"""Durable per-answer transactions, hash-chain validation and a process-scoped lock."""
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))+'\n').encode('utf-8')


def digest(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def atomic(path: Path, payload: bytes) -> None:
    temp = path.with_name(path.name+'.pending')
    with temp.open('wb') as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def event(folder: Path, kind: str, **fields) -> None:
    row = {'event': kind, 'utc': datetime.now(timezone.utc).isoformat(), **fields}
    with (folder/'events.jsonl').open('ab') as stream:
        stream.write(encoded(row)); stream.flush(); os.fsync(stream.fileno())


@contextmanager
def session_lock(session: Path):
    # Locks are released by the OS even after kill/Ctrl+C; the inert file remains.
    with (session/'execution.lock').open('r+b') as stream:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_records(folder: Path, run: dict, ids: list[str]) -> list[dict]:
    records = []
    previous = digest(run)
    files = sorted((folder/'records').glob('*.json'))
    for index, path in enumerate(files):
        if index >= len(ids):
            raise ValueError('Unknown or duplicate prediction ID')
        record = read(path)
        expected = f'{index:03d}-{ids[index]}.json'
        checksum = record.get('sha256')
        content = {k: v for k, v in record.items() if k != 'sha256'}
        if (path.name != expected or record.get('id') != ids[index] or record.get('run_id') != run['run_id']
                or not isinstance(record.get('response'), str) or record.get('previous_sha256') != previous
                or checksum != digest(content)):
            raise ValueError('Prediction sequence/hash/run identity mismatch')
        records.append(record); previous = checksum
    return records


def commit_record(folder: Path, run: dict, ids: list[str], records: list[dict], response: str, details: dict) -> None:
    index = len(records)
    if index >= len(ids) or not isinstance(response, str):
        raise ValueError('Unexpected prediction or response type')
    path = folder/'records'/f'{index:03d}-{ids[index]}.json'
    if path.exists():
        raise FileExistsError('Refusing to regenerate a committed response')
    record = {'id': ids[index], 'run_id': run['run_id'], 'response': response, 'details': details,
              'previous_sha256': records[-1]['sha256'] if records else digest(run)}
    record['sha256'] = digest(record)
    atomic(path, encoded(record))  # Commit point. No later failure regenerates this ID.
    records.append(record)
    publish_predictions(folder, records)


def publish_predictions(folder: Path, records: list[dict]) -> None:
    atomic(folder/'predictions.jsonl', b''.join(encoded({'id': r['id'], 'response': r['response']}) for r in records))


def check_predictions(folder: Path, records: list[dict]) -> None:
    expected = b''.join(encoded({'id': r['id'], 'response': r['response']}) for r in records)
    if (folder/'predictions.jsonl').read_bytes() != expected:
        raise ValueError('Predictions differ from committed raw responses')
