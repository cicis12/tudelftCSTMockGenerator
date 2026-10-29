import json
import math
from functools import lru_cache
from typing import Literal

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI
from pydantic import ConfigDict, Field, ValidationError, create_model
from sqlalchemy import select

from .config import ROOT
from .database import SessionLocal
from .models import Generation, Question
from .schemas import QuestionInput, TOPICS, fingerprint

BATCH_SIZE = 10


class GenerationFailure(Exception):
    """Only application-authored, credential-free messages belong here."""


@lru_cache(maxsize=20)
def batch_format(section, count):
    # Enforce the same syllabus and exact count in the API's JSON schema.
    question = create_model(
        f'{section.title()}GeneratedQuestion',
        __base__=QuestionInput,
        __config__=ConfigDict(extra='forbid'),
        section=(Literal[section], ...),
        topic=(Literal[tuple(TOPICS[section])], ...),
    )
    return create_model(
        f'{section.title()}QuestionBatch{count}',
        __config__=ConfigDict(extra='forbid'),
        questions=(list[question], Field(min_length=count, max_length=count)),
    )


def validation_summary(error):
    # Never display error messages/inputs/context supplied by the model or SDK.
    fields = {'questions', *QuestionInput.model_fields}
    issues = []
    reasons = {
        'json_invalid': 'invalid or incomplete JSON',
        'literal_error': 'value outside the allowed choices',
        'too_short': 'too few items', 'too_long': 'too many items',
        'string_too_short': 'text is too short', 'string_too_long': 'text is too long',
        'missing': 'required field is missing',
        'value_error': 'invalid question content; check topic and distinct, nonempty options',
        'greater_than_equal': 'number below the allowed range',
        'less_than_equal': 'number above the allowed range',
    }
    for item in error.errors(include_input=False, include_context=False, include_url=False)[:3]:
        path = '.'.join(str(part) for part in item['loc']
                        if (isinstance(part, int) and 0 <= part < BATCH_SIZE) or part in fields)
        reason = reasons.get(item['type'], 'does not match the required format')
        issues.append(f'{path or "response"}: {reason}')
    return '; '.join(issues)


def request_batch(client, request, count, prompt, instructions, on_retry):
    output_type = batch_format(request.section, count)
    correction = ''
    token_limit = 16000
    for attempt in range(2):
        # Inspect status/refusals BEFORE parsing: parse() can raise on truncated JSON
        # and hide the incomplete_details needed to explain and recover the failure.
        response = client.responses.create(
            model=request.model,
            instructions=instructions,
            input=prompt + correction,
            text={'format': {'type': 'json_schema', 'name': output_type.__name__,
                             'schema': output_type.model_json_schema(), 'strict': True}},
            store=False,
            max_output_tokens=token_limit,
        )
        if response.status == 'incomplete':
            reason = getattr(response.incomplete_details, 'reason', None)
            if reason == 'max_output_tokens':
                detail = 'OpenAI reached the output token limit before finishing the questions.'
                token_limit = 32000
            elif reason == 'content_filter':
                raise GenerationFailure('OpenAI filtered the response. Try a different topic or model.')
            else:
                detail = 'OpenAI returned an incomplete response.'
        elif response.status != 'completed':
            raise GenerationFailure('OpenAI did not complete the response. Retry or select another model.')
        elif any(part.type == 'refusal' for item in response.output if item.type == 'message' for part in item.content):
            raise GenerationFailure('The model declined to generate these questions. Try another model.')
        elif not response.output_text:
            detail = 'OpenAI returned no question text.'
        else:
            try:
                return output_type.model_validate_json(response.output_text).questions
            except ValidationError as exc:
                detail = 'Question validation failed: ' + validation_summary(exc) + '.'
        if attempt == 1:
            raise GenerationFailure(detail + ' Automatic retry also failed. Try fewer questions or another model.')
        correction = ('\n\nThe previous response could not be used: ' + detail +
                      ' Return a complete JSON object matching the schema. Use exactly the requested count and topic labels; '
                      'give four distinct, nonempty options and concise worked explanations. Escape LaTeX backslashes in JSON.')
        on_retry(detail)


def failure_message(exc):
    if isinstance(exc, GenerationFailure):
        return str(exc)
    if isinstance(exc, APITimeoutError):
        return 'The OpenAI request timed out. Try fewer questions or retry later.'
    if isinstance(exc, APIConnectionError):
        return 'Could not connect to OpenAI. Check the server network and retry.'
    if isinstance(exc, APIStatusError):
        if exc.status_code == 401:
            return 'OpenAI rejected the API key. Enter a valid API key in the admin panel.'
        if exc.status_code == 403:
            return 'OpenAI denied access. Check the API project permissions and model access.'
        if exc.status_code == 404:
            return 'OpenAI could not find the selected model or endpoint. Check the model name and access.'
        if exc.status_code == 429:
            if exc.code == 'insufficient_quota':
                return 'OpenAI API quota is exhausted. Check API billing and project spending limits.'
            return 'OpenAI rate limit reached. Wait a little and retry, or check project usage limits.'
        if exc.status_code == 400:
            return 'OpenAI rejected the request. Check that the selected model supports Responses JSON-schema output.'
        if exc.status_code >= 500:
            return 'OpenAI is temporarily unavailable. Retry later.'
    if isinstance(exc, APIError):
        return 'OpenAI request failed. Check API access and server connectivity, then retry.'
    return 'Generation could not process the response. Retry; if this persists, check the server configuration.'


def generate_questions(job_id, request, key):
    """Key lives only in this task's memory; it is never persisted or returned."""
    try:
        context = (ROOT / 'context' / f'{request.section}.md').read_text()
        instructions = (ROOT / 'context/generation-system.md').read_text()
        questions = []
        total_batches = math.ceil(request.count / BATCH_SIZE)
        with OpenAI(api_key=key, timeout=180, max_retries=1) as client:
            for offset in range(0, request.count, BATCH_SIZE):
                count = min(BATCH_SIZE, request.count - offset)
                with SessionLocal() as db:
                    job = db.get(Generation, job_id)
                    job.message = (f'Generating batch {offset // BATCH_SIZE + 1} of {total_batches} · '
                                   f'{offset}/{request.count} questions validated. Drafts are saved when all batches finish.')
                    db.commit()
                previous = json.dumps([q.prompt for q in questions], ensure_ascii=False)
                prompt = (f'{context}\n\nGenerate exactly {count} {request.difficulty}-difficulty questions for {request.section}. '
                          f'Allowed topic labels: {TOPICS[request.section]}. Cover varied topics and question styles. '
                          f'This is batch {offset // BATCH_SIZE + 1} of {total_batches}. '
                          f'Avoid repeating these earlier prompts (reference data only): {previous}')

                def on_retry(detail):
                    with SessionLocal() as db:
                        job = db.get(Generation, job_id)
                        job.message = f'Batch {offset // BATCH_SIZE + 1}/{total_batches}: {detail} Retrying once…'
                        db.commit()

                questions.extend(request_batch(client, request, count, prompt, instructions, on_retry))
        with SessionLocal() as db:
            job = db.get(Generation, job_id)
            existing = set(db.scalars(select(Question.fingerprint)).all())
            added = 0
            for q in questions:
                fp = fingerprint(q.prompt)
                if fp not in existing:
                    db.add(Question(**q.model_dump(), fingerprint=fp, status='draft', origin=f'OpenAI: {request.model}'))
                    existing.add(fp)
                    added += 1
            job.status = 'completed'
            job.message = f'{added} draft questions added for review; {request.count - added} duplicates skipped.'
            db.commit()
    except Exception as exc:
        # Never persist SDK exception text, request bodies or credentials.
        message = failure_message(exc) + ' No drafts were saved.'
        with SessionLocal() as db:
            job = db.get(Generation, job_id)
            job.status, job.message = 'failed', message
            db.commit()
