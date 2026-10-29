import random
import time

from fastapi import HTTPException
from sqlalchemy import select

from .config import settings
from .models import Attempt, AttemptProfile, Item, Question
from .progress import cooldowns, progress_summary, record_results
from .schemas import DURATIONS


def question_snapshot(q):
    return {k: getattr(q, k) for k in ('prompt', 'options', 'correct_index', 'explanation', 'topic', 'difficulty', 'source_ref')}


def choose_questions(db, section, count, exclude=(), profile=None):
    pool = list(db.scalars(select(Question).where(Question.section == section, Question.status == 'published')).all())
    if not pool:
        raise HTTPException(409, f'No published {section} questions are available.')
    resting = cooldowns(db, profile)
    pool = [q for q in pool if q.id not in resting]
    if not pool:
        return []
    available = [q for q in pool if q.id not in exclude]
    if count == 1:
        return [random.choice(available or pool)]
    # Round-robin topics for balanced coverage, then order by difficulty.
    groups = {}
    random.shuffle(pool)
    for q in pool:
        groups.setdefault(q.topic, []).append(q)
    result = []
    while len(result) < min(count, len(pool)):
        topics = list(groups)
        random.shuffle(topics)
        for topic in topics:
            if groups[topic] and len(result) < count:
                result.append(groups[topic].pop())
        if all(not group for group in groups.values()):
            break
    return sorted(result, key=lambda q: {'easy': 0, 'medium': 1, 'hard': 2}[q.difficulty])


def all_items(db, attempt):
    return list(db.scalars(select(Item).where(Item.attempt_id == attempt.id).order_by(Item.position)).all())


def add_practice_item(db, attempt):
    items = all_items(db, attempt)
    profile = attempt_profile(db, attempt)
    section = attempt.sections[attempt.active_section]
    choices = choose_questions(db, section, 1, {i.question_id for i in items if i.section == section}, profile)
    if not choices:
        # In combined practice, use the other section before ending the session.
        for index, other in enumerate(attempt.sections):
            if other == section:
                continue
            choices = choose_questions(db, other, 1, {i.question_id for i in items if i.section == other}, profile)
            if choices:
                attempt.active_section, section = index, other
                attempt.block += 1
                attempt.deadline = time.time() + DURATIONS[other]
                break
        if not choices:
            finish(db, attempt)
            return None
    q = choices[0]
    item = Item(attempt_id=attempt.id, question_id=q.id, position=len(items), section=section,
                block=attempt.block, snapshot=question_snapshot(q))
    db.add(item)
    db.flush()
    return item


def attempt_profile(db, attempt):
    binding = db.get(AttemptProfile, attempt.id)
    return binding.profile if binding else f'guest:{attempt.owner}'


def start_attempt(db, owner, data, profile=None):
    sections = ['math', 'logic'] if data.section == 'both' else [data.section]
    profile = profile or f'guest:{owner}'
    # Validate the whole pool before committing an attempt.
    pools = {s: choose_questions(db, s, max(1, getattr(settings, f'{s}_question_count')), profile=profile) for s in sections}
    for section, pool in pools.items():
        if not pool:
            raise HTTPException(409, f'You are caught up with {section}. Correctly answered questions are resting. Choose another section or return when they are ready for review.')
    attempt = Attempt(owner=owner, mode=data.mode, sections=sections, deadline=time.time() + DURATIONS[sections[0]])
    db.add(attempt)
    db.flush()
    db.add(AttemptProfile(attempt_id=attempt.id, profile=profile))
    db.flush()
    if data.mode == 'timed':
        position = 0
        for section in sections:
            for q in pools[section]:
                db.add(Item(attempt_id=attempt.id, question_id=q.id, position=position,
                            section=section, snapshot=question_snapshot(q)))
                position += 1
    else:
        add_practice_item(db, attempt)
    db.commit()
    return attempt


def finish(db, attempt, at=None):
    attempt.status = 'finished'
    attempt.finished_at = time.time() if at is None else at
    record_results(db, attempt)


def advance(db, attempt, at):
    if attempt.mode == 'timed':
        if attempt.active_section + 1 >= len(attempt.sections):
            finish(db, attempt, at)
            return
        attempt.active_section += 1
    else:
        for item in all_items(db, attempt):
            if item.block == attempt.block:
                item.submitted = True
        attempt.active_section = (attempt.active_section + 1) % len(attempt.sections)
        attempt.block += 1
    attempt.deadline = at + DURATIONS[attempt.sections[attempt.active_section]]


def enforce_deadline(db, attempt):
    now = time.time()
    if attempt.mode == 'infinite' and attempt.status == 'active' and now >= attempt.deadline:
        # Skip complete cycles when returning after a long absence, without generating phantom questions.
        for item in all_items(db, attempt):
            if item.block == attempt.block:
                item.submitted = True
        cycle = sum(DURATIONS[s] for s in attempt.sections)
        cycles = int((now - attempt.deadline) // cycle)
        if cycles:
            attempt.deadline += cycles * cycle
            attempt.block += cycles * len(attempt.sections)
    while attempt.status == 'active' and now >= attempt.deadline:
        advance(db, attempt, attempt.deadline)
    if attempt.mode == 'infinite' and attempt.status == 'active':
        if not any(i.block == attempt.block for i in all_items(db, attempt)):
            add_practice_item(db, attempt)
    db.flush()


def public_item(item, reveal=False):
    data = {k: v for k, v in item.snapshot.items() if reveal or k not in ('correct_index', 'explanation', 'source_ref')}
    data.update(id=item.id, position=item.position, section=item.section, block=item.block,
                answer=item.answer, submitted=item.submitted, flagged=item.flagged)
    if reveal:
        data['correct'] = item.answer == item.snapshot['correct_index']
    return data


def serialize_attempt(db, attempt):
    items = all_items(db, attempt)
    complete = attempt.status == 'finished'
    section = attempt.sections[attempt.active_section]
    visible = items if complete else [i for i in items if i.section == section and (attempt.mode == 'timed' or i.block == attempt.block)]
    result = dict(id=attempt.id, mode=attempt.mode, sections=attempt.sections, section=section,
                  status=attempt.status, deadline=attempt.deadline, server_time=time.time(),
                  block=attempt.block, created_at=attempt.created_at,
                  items=[public_item(i, complete or (attempt.mode == 'infinite' and i.submitted)) for i in visible])
    if complete or attempt.mode == 'infinite':
        scored = items if complete else [i for i in items if i.submitted]
        result['scores'] = {s: {'correct': sum(i.answer == i.snapshot['correct_index'] for i in scored if i.section == s),
                                'total': sum(i.section == s for i in scored)} for s in attempt.sections}
    if complete:
        result['progress'] = progress_summary(db, attempt_profile(db, attempt))
    return result
