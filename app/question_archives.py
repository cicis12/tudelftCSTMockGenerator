"""Portable, versioned question archives; ZIP contents are never extracted to disk."""
import io
import json
import time
import zipfile
import zlib
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import Question
from .schemas import QuestionInput, fingerprint

MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 50 * 1024 * 1024


class ArchivedQuestion(QuestionInput):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['draft', 'published', 'rejected']
    origin: str = Field(min_length=1, max_length=100)
    created_at: float = Field(ge=0, allow_inf_nan=False)


class QuestionArchive(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    format: Literal['cst-studio-questions']
    version: Literal[1]
    exported_at: float = Field(ge=0, allow_inf_nan=False)
    questions: list[ArchivedQuestion]


def export_questions(db):
    questions = db.scalars(select(Question).order_by(Question.id)).all()
    document = {
        'format': 'cst-studio-questions', 'version': 1, 'exported_at': time.time(),
        'questions': [
            {field: getattr(question, field) for field in ArchivedQuestion.model_fields}
            for question in questions
        ],
    }
    data = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
    if len(data) > MAX_JSON_BYTES:
        raise HTTPException(413, 'This question bank exceeds the 50 MiB archive content limit.')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('questions.json', data)
    result = buffer.getvalue()
    if len(result) > MAX_ZIP_BYTES:
        raise HTTPException(413, 'This question bank exceeds the 10 MiB ZIP limit.')
    return result


def read_archive(payload):
    if len(payload) > MAX_ZIP_BYTES:
        raise HTTPException(413, 'ZIP files must be no larger than 10 MiB.')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) != 1 or members[0].filename != 'questions.json':
                raise HTTPException(422, 'The ZIP must contain exactly one file named questions.json at its root.')
            member = members[0]
            if member.flag_bits & 1 or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise HTTPException(422, 'Use an unencrypted ZIP with standard compression.')
            if member.file_size > MAX_JSON_BYTES:
                raise HTTPException(413, 'Uncompressed questions.json must be no larger than 50 MiB.')
            with archive.open(member) as stream:
                content = stream.read(MAX_JSON_BYTES + 1)
            if len(content) > MAX_JSON_BYTES:
                raise HTTPException(413, 'Uncompressed questions.json must be no larger than 50 MiB.')
        return QuestionArchive.model_validate_json(content)
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_context=False)[0]
        location = '.'.join(str(part) for part in error['loc']) or 'archive'
        raise HTTPException(422, f'Invalid question archive at {location}: {error["msg"]}. No questions were imported.') from None
    except (zipfile.BadZipFile, zlib.error, OSError, EOFError, RuntimeError, NotImplementedError, ValueError):
        raise HTTPException(422, 'This file is not a readable question ZIP. No questions were imported.') from None


def import_questions(db, payload):
    document = read_archive(payload)
    known = set(db.scalars(select(Question.fingerprint)).all())
    added = 0
    for question in document.questions:
        fp = fingerprint(question.prompt)
        if fp in known:
            continue
        db.add(Question(**question.model_dump(), fingerprint=fp))
        known.add(fp)
        added += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'The question bank changed during import. No questions were imported; please retry.') from None
    return {'imported': added, 'skipped': len(document.questions) - added, 'total': len(document.questions)}
