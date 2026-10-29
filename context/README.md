# Source provenance and generation policy

The app sends `generation-system.md` and **only the selected section's curated context** with each OpenAI generation request. It does not upload the full PDFs or send student answers. This keeps the request bounded, avoids broken PDF font extraction, and excludes starred textbook sections explicitly. Drafts require human review before publication; JSON validation cannot prove mathematical correctness.

Sources reviewed on 2026-10-29:

| Source | Use |
| --- | --- |
| `sources/brochure.pdf`, printed pp. 8–10 | Two sections, 60/45 minutes, equal weighting, rules, preparation scope |
| `sources/syllabus.pdf`, pp. 1–3 | Seven maths subject areas, exact answers, no calculator |
| `sources/formulas.pdf`, v2019.1, pp. 1–2 | Original formula panel, trigonometry and integral table |
| `sources/textbook.pdf`, contents and Chapter 2 | Non-starred logic subsections, including §2.3.4 |
| https://ocw.tudelft.nl/courses/pre-university-calculus/ | Official TU Delft course outline; functions, equations, differentiation, integration |
| https://www.edx.org/learn/calculus/delft-university-of-technology-pre-university-calculus | DelftX catalogue scope, including analytic geometry |
| https://developers.openai.com/api/docs/guides/structured-outputs | Responses API structured output integration |

The local brochure is authoritative for this app. Search results include older three-section formats that conflict with it; those were not adopted. The original question count and complete response-format specification were not established by these sources. The defaults of 24 maths and 20 logic questions, four-option MCQs, one point per correct answer and no negative marking are **mock-app choices**. Scores are raw practice percentages, never admissions rankings or official normalized CST scores. Infinite mode repeats 60/45-minute practice blocks; selected sections alternate when both are chosen. Repeats are possible once the published question pool is exhausted.

Starter questions are original practice exercises, with a mix of conceptual items and parameterized families. They cover all topic categories but are not a calibrated representation of official exam difficulty. Keep the supplied PDFs with their existing attribution; no license to redistribute those documents is added by this project.

To audit PDF text locally, install Poppler and run `scripts/extract_sources.sh`. These extraction files are diagnostic only and intentionally ignored by Git. The curated context should be reviewed when the syllabus changes.
