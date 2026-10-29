import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Section = Literal['math', 'logic']
TOPICS = {
    'math': ['Functions and graphs', 'Algebra and equations', 'Differential calculus', 'Integral calculus', 'Trigonometry', 'Geometry', 'Vectors'],
    'logic': ['Propositional logic', 'Boolean algebra', 'Disjunctive normal form', 'Predicate logic', 'Deduction'],
}
DURATIONS = {'math': 3600, 'logic': 2700}
MAX_GENERATED_QUESTIONS = 100


def fingerprint(prompt):
    return hashlib.sha256(re.sub(r'\s+', ' ', prompt.strip().lower()).encode()).hexdigest()


class QuestionInput(BaseModel):
    section: Section
    topic: str = Field(min_length=1, max_length=80)
    difficulty: Literal['easy', 'medium', 'hard']
    prompt: str = Field(min_length=10, max_length=5000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=20, max_length=8000)
    source_ref: str = Field(min_length=3, max_length=250)

    @model_validator(mode='after')
    def check_content(self):
        if self.topic not in TOPICS[self.section]:
            raise ValueError('Topic is outside the selected section syllabus.')
        normalized = [x.strip().casefold() for x in self.options]
        if not all(normalized) or len(set(normalized)) != 4 or any(len(x) > 2000 for x in self.options):
            raise ValueError('Provide four distinct, nonempty options of at most 2000 characters.')
        return self


class QuestionBatch(BaseModel):
    questions: list[QuestionInput]


class StartInput(BaseModel):
    section: Literal['math', 'logic', 'both']
    mode: Literal['timed', 'infinite']
    accepted_rules: bool


class AnswerInput(BaseModel):
    answer: int | None = Field(default=None, ge=0, le=3)
    flagged: bool = False


class GenerateInput(BaseModel):
    section: Section
    count: int = Field(default=5, ge=1, le=MAX_GENERATED_QUESTIONS)
    difficulty: Literal['easy', 'medium', 'hard', 'mixed'] = 'mixed'
    model: str = Field(default='gpt-4.1-mini', min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9._:-]+$')
    api_key: str = Field(default='', max_length=500)


class LoginInput(BaseModel):
    password: str = Field(max_length=500)


class LearnerCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=24, pattern=r'^[A-Za-z0-9_]+$')
    password: str = Field(min_length=12, max_length=128)
