import time

from sqlalchemy import func, select

from .config import settings
from .models import AttemptProfile, Item, Question, QuestionResult


def record_results(db, attempt):
    """Each immutable answer contributes once. Active mock answers remain private."""
    binding = db.get(AttemptProfile, attempt.id)
    if not binding:
        binding = AttemptProfile(attempt_id=attempt.id, profile=f'guest:{attempt.owner}')
        db.add(binding)
        db.flush()
    if attempt.mode == 'timed' and attempt.status != 'finished':
        return
    items = db.scalars(select(Item).outerjoin(QuestionResult, QuestionResult.item_id == Item.id).where(
        Item.attempt_id == attempt.id, Item.answer.is_not(None), QuestionResult.item_id.is_(None),
    )).all()
    for item in items:
        if attempt.mode == 'infinite' and not item.submitted:
            continue
        db.add(QuestionResult(item_id=item.id, profile=binding.profile, question_id=item.question_id,
                              correct=item.answer == item.snapshot['correct_index'],
                              recorded_at=attempt.finished_at if attempt.status == 'finished' else time.time()))
    db.flush()


def cooldowns(db, profile):
    if not profile:
        return {}
    duration = settings.correct_answer_cooldown_days * 86400
    rows = db.execute(select(QuestionResult.question_id, func.max(QuestionResult.recorded_at))
                      .where(QuestionResult.profile == profile, QuestionResult.correct.is_(True))
                      .group_by(QuestionResult.question_id)).all()
    now = time.time()
    return {qid: at + duration for qid, at in rows if at + duration > now}


def progress_summary(db, profile):
    resting = cooldowns(db, profile)
    published = db.scalars(select(Question).where(Question.status == 'published')).all()
    results = db.execute(select(QuestionResult.question_id, QuestionResult.correct)
                         .where(QuestionResult.profile == profile)).all()
    correct_ids = {qid for qid, correct in results if correct}
    sections = {}
    for section in ('math', 'logic'):
        ids = {q.id for q in published if q.section == section}
        paused = ids & resting.keys()
        sections[section] = {'total': len(ids), 'available': len(ids - paused), 'resting': len(paused),
                             'correct_questions': len(ids & correct_ids),
                             'next_review_at': min((resting[qid] for qid in paused), default=None)}
    return {'cooldown_days': settings.correct_answer_cooldown_days, 'answered': len(results),
            'correct_answers': sum(correct for _, correct in results),
            'correct_questions': len(correct_ids), 'sections': sections}
