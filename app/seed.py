"""Original practice material, independently authored against the supplied syllabus."""
import random

from sqlalchemy import select

from .models import Question
from .schemas import QuestionInput, fingerprint


def seed_questions():
    rows = []

    def add(section, topic, prompt, choices, explanation, difficulty='medium', ref=None):
        # Authoring convention: first choice is correct; fixed shuffle avoids position bias.
        correct = choices[0]
        random.Random(prompt).shuffle(choices)
        rows.append(QuestionInput(section=section, topic=topic, prompt=prompt,
            options=choices, correct_index=choices.index(correct), explanation=explanation,
            difficulty=difficulty, source_ref=ref or ('syllabus.pdf §' + str({
                'Functions and graphs': 1, 'Algebra and equations': 2, 'Differential calculus': 3,
                'Integral calculus': 4, 'Trigonometry': 5, 'Geometry': 6, 'Vectors': 7}.get(topic, ''))
                if section == 'math' else 'textbook.pdf Chapter 2')))

    for a in [3, 4, 5, 6, 7, 8]:
        add('math', 'Functions and graphs', rf'What is the domain of \(f(x)=\sqrt{{x-{a}}}\)?',
            [rf'\([{a},\infty)\)', rf'\(( {a},\infty)\)', rf'\(( -\infty,{a}]\)', r'\(\mathbb{R}\)'],
            f'The expression under a real square root must be nonnegative. Thus x − {a} ≥ 0, so x ≥ {a}.', 'easy')
        add('math', 'Algebra and equations', rf'Solve \(x^2-{a+2}x+{2*a}=0\).',
            [rf'\(x=2\text{{ or }}x={a}\)', rf'\(x=-2\text{{ or }}x=-{a}\)', rf'\(x=0\text{{ or }}x={a+2}\)', rf'\(x=1\text{{ or }}x={2*a}\)'],
            rf'Factor the polynomial as \((x-2)(x-{a})\). A product is zero when at least one factor is zero. The roots are 2 and {a}.', 'easy')
        add('math', 'Differential calculus', rf'Let \(f(x)=( {a}x+1)^3\). Find \(f\prime(0)\).',
            [str(3*a), str(a), str(3*a*a), str(2*a)],
            rf'The chain rule gives \(f\prime(x)=3({a}x+1)^2\cdot {a}\). At x = 0 this is {3*a}.')
        add('math', 'Integral calculus', rf'Evaluate \(\int_0^2 {a}x^2\,dx\).',
            [rf'\(\frac{{{8*a}}}{{3}}\)', str(4*a), str(8*a), rf'\(\frac{{{2*a}}}{{3}}\)'],
            rf'An antiderivative is \({a}x^3/3\). Evaluating at 2 and 0 gives \({8*a}/3\).')
        add('math', 'Trigonometry', rf'What is the period of \(f(t)=3\sin({a}t)+2\)?',
            [rf'\(\frac{{2\pi}}{{{a}}}\)', rf'\({2*a}\pi\)', r'\(2\pi\)', rf'\(\frac{{\pi}}{{{a}}}\)'],
            rf'Sine repeats when its argument increases by \(2\pi\). Therefore \({a}T=2\pi\), giving \(T=2\pi/{a}\).', 'easy')
        add('math', 'Geometry', rf'A circle has centre \(({a},-2)\) and radius 3. Which is its equation?',
            [rf'\((x-{a})^2+(y+2)^2=9\)', rf'\((x+{a})^2+(y-2)^2=9\)', rf'\((x-{a})^2+(y+2)^2=3\)', rf'\((x-{a})^2+(y-2)^2=9\)'],
            rf'The equation is \((x-h)^2+(y-k)^2=r^2\). Substitute h = {a}, k = −2 and r = 3.', 'easy')
        add('math', 'Vectors', rf'For \(\mathbf{{u}}=({a},2)\) and \(\mathbf{{v}}=(2,-{a})\), find \(\mathbf{{u}}\cdot\mathbf{{v}}\).',
            ['0', str(4*a), str(2*a), str(-2*a)],
            rf'The dot product is \({a}\cdot2+2\cdot(-{a})=0\). The nonzero vectors are therefore perpendicular.', 'easy')

    extra_math = [
        ('Functions and graphs', r'For \(f(x)=\frac{2x+1}{x-3}\), which pair gives the vertical and horizontal asymptotes?', [r'\(x=3,\ y=2\)', r'\(x=-3,\ y=2\)', r'\(x=3,\ y=1\)', r'\(x=2,\ y=3\)'], 'The denominator vanishes at x = 3 and the numerator does not. The ratio of leading coefficients is 2, which gives the horizontal asymptote.'),
        ('Functions and graphs', r'Find the inverse of \(f(x)=e^{2x}-3\).', [r'\(f^{-1}(x)=\frac12\ln(x+3)\)', r'\(f^{-1}(x)=\ln(x+3)\)', r'\(f^{-1}(x)=\frac12\ln(x)-3\)', r'\(f^{-1}(x)=e^{x/2}+3\)'], r'Write \(y=e^{2x}-3\), then \(\ln(y+3)=2x\). Solve for x and exchange the variables. The inverse has domain x > −3.'),
        ('Functions and graphs', r'Evaluate \(\lim_{x\to 2}\frac{x^2-4}{x-2}\).', ['4', '0', '2', 'The limit does not exist'], 'For x ≠ 2, factor and cancel x − 2 to obtain x + 2. Its limit as x approaches 2 is 4.'),
        ('Algebra and equations', r'Solve \(\ln(x-1)+\ln(x+1)=\ln(8)\).', ['x = 3', 'x = −3 or x = 3', 'x = 9', 'x = √8'], 'The domain requires x > 1. Combining logarithms gives x² − 1 = 8, so x² = 9. Only x = 3 is in the domain.'),
        ('Algebra and equations', r'Solve \(\frac{x-1}{x+2}\leq 0\).', [r'\((-2,1]\)', r'\([-2,1]\)', r'\(( -\infty,-2)\cup[1,\infty)\)', r'\((-2,1)\)'], 'The critical values are −2 (undefined) and 1 (zero). The quotient is negative between them. Include 1, but exclude −2.'),
        ('Algebra and equations', 'Solve the system 2x + y = 7 and x − y = 2.', ['x = 3, y = 1', 'x = 1, y = 5', 'x = 2, y = 3', 'x = 4, y = −1'], 'Adding the equations gives 3x = 9. Thus x = 3, and substituting into x − y = 2 gives y = 1.'),
        ('Differential calculus', r'Find the slope of the tangent to \(f(x)=x\ln(x)\) at \(x=1\).', ['1', '0', '2', '−1'], r'By the product rule, \(f\prime(x)=\ln(x)+1\). Since ln(1) = 0, the tangent slope is 1.'),
        ('Differential calculus', 'A rectangle has perimeter 20. What is its greatest possible area?', ['25', '20', '50', '100'], 'With sides x and 10 − x, the area is A(x) = 10x − x². Its derivative vanishes at x = 5, and A″ = −2 confirms a maximum. The area is 25.'),
        ('Differential calculus', r'Where does \(f(x)=x^3-6x^2+9x\) have a local minimum?', ['x = 3', 'x = 1', 'x = 0', 'x = 2'], 'The derivative is 3(x − 1)(x − 3). At x = 3, the second derivative 6x − 12 is positive, so this stationary point is a local minimum.'),
        ('Differential calculus', r'For \(f(x)=\frac{x}{x+1}\), find \(f\prime(x)\) where \(x\ne-1\).', [r'\(\frac{1}{(x+1)^2}\)', r'\(\frac{-1}{(x+1)^2}\)', r'\(\frac{1}{x+1}\)', r'\(\frac{x}{(x+1)^2}\)'], r'The quotient rule gives \(((x+1)-x)/(x+1)^2=1/(x+1)^2\).'),
        ('Integral calculus', r'Find the mean value of \(f(x)=x^2\) on \([0,3]\).', ['3', '9', '9/2', '1'], 'The mean value is the definite integral divided by the interval length: (1/3) × [x³/3] from 0 to 3 = 9/3 = 3.'),
        ('Integral calculus', r'The region under \(y=x\), from x = 0 to x = 2, is rotated about the x-axis. Find its volume.', [r'\(8\pi/3\)', r'\(4\pi\)', r'\(2\pi\)', r'\(16\pi/3\)'], r'The disc method gives \(V=\pi\int_0^2 x^2\,dx=\pi[x^3/3]_0^2=8\pi/3\).'),
        ('Integral calculus', r'Evaluate \(\int_0^{\pi/4}2\cos(2x)\,dx\).', ['1', '2', '0', '1/2'], 'An antiderivative is sin(2x). At the endpoints the difference is sin(π/2) − sin(0) = 1.'),
        ('Trigonometry', r'Solve \(\sin(x)=1/2\) for \(0\leq x<2\pi\).', [r'\(x=\pi/6\text{ or }5\pi/6\)', r'\(x=\pi/3\text{ or }2\pi/3\)', r'\(x=\pi/6\text{ or }7\pi/6\)', r'\(x=5\pi/6\text{ or }7\pi/6\)'], 'Sine is positive in quadrants I and II. The reference angle is π/6, so the two solutions are π/6 and π − π/6 = 5π/6.'),
        ('Trigonometry', r'If \(\cos(x)=3/5\) and \(0<x<\pi/2\), find \(\sin(2x)\).', ['24/25', '12/25', '7/25', '4/5'], 'The Pythagorean identity and first-quadrant condition give sin(x) = 4/5. Then sin(2x) = 2 sin(x) cos(x) = 24/25.'),
        ('Geometry', 'A triangle has sides 3 and 5 enclosing an angle of 60°. Find the square of the third side.', ['19', '34', '49', '4'], 'By the cosine rule, c² = 3² + 5² − 2·3·5·cos(60°) = 34 − 15 = 19.'),
        ('Geometry', r'The line \(y=x\) intersects the circle \(x^2+y^2=8\). What are the intersection points?', ['(2, 2) and (−2, −2)', '(√8, √8) and (−√8, −√8)', '(2, −2) and (−2, 2)', '(4, 4) and (−4, −4)'], 'Substitute y = x into the circle equation: 2x² = 8. Thus x = ±2; the y coordinate is the same as x.'),
        ('Vectors', r'A point has position \(\mathbf{r}(t)=(t^2,3t)\). What is its speed at t = 2?', ['5', '7', '25', '√13'], 'Differentiate the position to obtain velocity (2t, 3). At t = 2 this is (4, 3), whose length is √(16 + 9) = 5.'),
        ('Vectors', r'Find the angle between \(\mathbf{u}=(1,0)\) and \(\mathbf{v}=(1,1)\).', [r'\(\pi/4\)', r'\(\pi/2\)', r'\(\pi/3\)', '0'], 'The cosine of the angle is (u·v)/(‖u‖‖v‖) = 1/√2. The angle in [0, π] with this cosine is π/4.'),
    ]
    for topic, prompt, options, explanation in extra_math:
        add('math', topic, prompt, options, explanation)

    logic = [
        ('Propositional logic', 'When is the implication p → q false?', ['p is true and q is false', 'p is false and q is true', 'p and q are both false', 'p and q are both true'], 'An implication fails only when its premise is true and its conclusion is false. In all other assignments the material implication is true.'),
        ('Propositional logic', 'Which proposition is equivalent to p → q?', ['¬p ∨ q', 'p ∧ q', 'p ∨ ¬q', '¬p ∧ q'], 'The implication and ¬p ∨ q are both false exactly when p is true and q is false. Their truth tables therefore agree.'),
        ('Propositional logic', 'Which is the contrapositive of p → q?', ['¬q → ¬p', 'q → p', '¬p → ¬q', 'p → ¬q'], 'The contrapositive reverses the direction and negates both propositions. It is logically equivalent to the original implication.'),
        ('Propositional logic', 'Translate “Access is granted only if the token is valid.” Let A mean access is granted and T mean the token is valid.', ['A → T', 'T → A', 'A ∧ T', '¬A → T'], '“A only if T” makes T a necessary condition for A. Thus whenever access is granted the token must be valid: A → T.'),
        ('Propositional logic', 'Which proposition is a tautology?', ['p ∨ ¬p', 'p ∧ ¬p', 'p → ¬p', 'p ∧ q'], 'By excluded middle, p ∨ ¬p is true whether p is true or false. The other options can be false.'),
        ('Propositional logic', 'When is p ⊕ q (exclusive or) true?', ['Exactly one of p and q is true', 'At least one is true, including both', 'Both are true', 'Both are false'], 'Exclusive or is true when the operands have different truth values. Unlike inclusive or, it is false when both operands are true.'),
        ('Propositional logic', 'Which proposition is equivalent to ¬(p → q)?', ['p ∧ ¬q', '¬p ∨ q', '¬p ∧ q', 'p → ¬q'], 'Replace the implication by ¬p ∨ q and negate it. De Morgan’s law yields p ∧ ¬q.'),
        ('Propositional logic', 'How many rows does a full truth table with four distinct propositional variables have?', ['16', '8', '4', '32'], 'Each of the four independent variables has two truth values. Thus a complete truth table has 2⁴ = 16 assignments.'),
        ('Boolean algebra', 'Simplify p ∨ (p ∧ q).', ['p', 'q', 'p ∧ q', 'p ∨ q'], 'The absorption law gives p ∨ (p ∧ q) = p. If p is true, both sides are true; if p is false, both sides are false.'),
        ('Boolean algebra', 'Which expression equals ¬(p ∧ q)?', ['¬p ∨ ¬q', '¬p ∧ ¬q', 'p ∨ q', '¬p ∨ q'], 'De Morgan’s law changes a negated conjunction into a disjunction of the negations.'),
        ('Boolean algebra', 'Simplify (p ∧ q) ∨ (p ∧ ¬q).', ['p', 'q', '¬p', 'p ∧ q'], 'Factor p using distributivity: p ∧ (q ∨ ¬q). The parenthesis is true, so the expression is p.'),
        ('Boolean algebra', 'Simplify (p ∨ q) ∧ (p ∨ ¬q).', ['p', 'q', 'p ∨ q', 'False'], 'Distribute to obtain p ∨ (q ∧ ¬q). Since q ∧ ¬q is false, the result is p.'),
        ('Boolean algebra', 'Which expression is equivalent to p ∧ (q ∨ r)?', ['(p ∧ q) ∨ (p ∧ r)', '(p ∨ q) ∧ r', '(p ∧ q) ∧ r', 'p ∨ (q ∧ r)'], 'Conjunction distributes over disjunction. The term p must hold together with at least one of q and r.'),
        ('Disjunctive normal form', 'Which expression is in disjunctive normal form (DNF)?', ['(p ∧ ¬q) ∨ (¬p ∧ r)', '(p ∨ q) ∧ (¬p ∨ r)', '¬(p ∧ q)', 'p → (q ∧ r)'], 'DNF is a disjunction of conjunctions of literals. A literal is a variable or its negation; the first expression has precisely this structure.'),
        ('Disjunctive normal form', 'A proposition is true only for (p, q) = (true, false) or (false, true). Which DNF represents it?', ['(p ∧ ¬q) ∨ (¬p ∧ q)', '(p ∧ q) ∨ (¬p ∧ ¬q)', 'p ∨ q', 'p ∧ q'], 'Create one conjunction for each true row, using a variable when it is true and its negation when false. Join those row terms with or.'),
        ('Disjunctive normal form', 'A truth table over p and q has exactly one true row: p = false, q = false. Which full DNF represents it?', ['¬p ∧ ¬q', 'p ∧ q', '¬p ∨ ¬q', 'p ∨ q'], 'The sole true row is represented by the conjunction of the two negated variables. That term is false for all other rows.'),
        ('Predicate logic', 'Negate ∀x P(x).', ['∃x ¬P(x)', '∀x ¬P(x)', '¬∃x P(x)', '∃x P(x)'], 'A universal statement is false when there is at least one counterexample. Negation switches ∀ to ∃ and negates the predicate.'),
        ('Predicate logic', 'Over the integers, which statement is true?', ['∀x ∃y (y > x)', '∃y ∀x (y > x)', '∀x (x > 0)', '∃x (x² < 0)'], 'For every integer x, choose y = x + 1. There is no single greatest integer, and an integer square cannot be negative.'),
        ('Predicate logic', 'Translate “Every student likes some book.” Use S(x), B(y), and L(x,y), over all people and objects.', ['∀x (S(x) → ∃y (B(y) ∧ L(x,y)))', '∃y (B(y) ∧ ∀x L(x,y))', '∀x (S(x) ∧ ∃y (B(y) ∧ L(x,y)))', '∀x ∀y ((S(x) ∧ B(y)) → L(x,y))'], 'For each object that is a student, require the existence of a book that student likes. The book may differ from student to student.'),
        ('Predicate logic', 'Which formula is the negation of ∀x ∃y R(x,y)?', ['∃x ∀y ¬R(x,y)', '∀x ∃y ¬R(x,y)', '∃x ∃y ¬R(x,y)', '∀y ∃x R(x,y)'], 'Move the negation inward through both quantifiers: ¬∀ becomes ∃¬ and ¬∃ becomes ∀¬. Finally negate the predicate.'),
        ('Predicate logic', 'On the domain {1, 2, 3}, let P(x) mean x is even. Which statement is true?', ['∃x P(x)', '∀x P(x)', '∀x ¬P(x)', '¬∃x P(x)'], 'The domain contains the even number 2, which witnesses ∃x P(x). The numbers 1 and 3 show the universal claim is false.'),
        ('Predicate logic', 'In the formula ∀x (P(x,y) → ∃z Q(x,z)), which variable is free?', ['y only', 'x only', 'z only', 'None'], 'The occurrences of x are bound by ∀x, and z is bound by ∃z. No quantifier binds y, so y is the only free variable.'),
        ('Predicate logic', 'Over an empty domain, what is the truth value of ∀x P(x)?', ['True, by vacuous truth', 'False, because there are no elements', 'True only if ∃x P(x)', 'It depends on the name of P'], 'There is no element that violates P. The universal statement is therefore vacuously true; the corresponding existential is false.'),
        ('Deduction', 'Given p → q and p, what follows by modus ponens?', ['q', '¬q', '¬p', 'q → ¬p'], 'Modus ponens applies an implication to an established premise. Since p holds and p implies q, q follows.'),
        ('Deduction', 'Given p → q and ¬q, what follows?', ['¬p', 'p', 'q', 'p ∧ q'], 'Modus tollens: if p held then q would hold, contradicting ¬q. Hence p must be false.'),
        ('Deduction', 'Which argument is invalid?', ['p → q; q; therefore p', 'p → q; p; therefore q', 'p → q; ¬q; therefore ¬p', 'p ∨ q; ¬p; therefore q'], 'Affirming the consequent is invalid: with p false and q true both premises hold but the conclusion p is false.'),
        ('Deduction', 'Assume ∀x (P(x) → Q(x)) and P(a). What must follow?', ['Q(a)', '∀x P(x)', '∀x Q(x)', '¬Q(a)'], 'Instantiate the universal premise at a to get P(a) → Q(a). Apply modus ponens with P(a) to obtain Q(a).'),
        ('Deduction', 'Given p ∨ q and ¬p, what can be concluded?', ['q', '¬q', 'p', 'p ∧ q'], 'At least one disjunct must hold. Since p is false, q must be true. This is disjunctive syllogism.'),
        ('Deduction', 'Which assignment disproves the argument p → q; ¬p; therefore ¬q?', ['p = false, q = true', 'p = true, q = false', 'p = true, q = true', 'p = false, q = false'], 'A counterexample makes all premises true and the conclusion false. With p false and q true, p → q and ¬p are true, but ¬q is false.'),
    ]
    for topic, prompt, options, explanation in logic:
        add('logic', topic, prompt, options, explanation,
            ref='textbook.pdf §' + {'Propositional logic': '2.1', 'Boolean algebra': '2.2', 'Disjunctive normal form': '2.3.4', 'Predicate logic': '2.4', 'Deduction': '2.5'}[topic])
    return rows


def seed_database(db):
    known = set(db.scalars(select(Question.fingerprint)).all())
    for q in seed_questions():
        fp = fingerprint(q.prompt)
        if fp not in known:
            db.add(Question(**q.model_dump(), fingerprint=fp, status='published', origin='original starter bank'))
            known.add(fp)
    db.commit()
