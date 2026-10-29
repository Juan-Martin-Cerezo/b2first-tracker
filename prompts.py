# -*- coding: utf-8 -*-
"""Official B2 First (Cambridge) Writing rubric and AI marker prompts.

Source: /home/juan/Descargas/b2-first/05-Handbooks/b2-first-handbook.pdf
PDF pages: 33–36 (printed numbering: 31–34).
"""

RUBRIC_SOURCE = "B2 First Handbook, pages 32-35 (Cambridge University Press)"

SCHEMA_KEYS = ("content", "communicative_achievement", "organisation", "language")
SCHEMA_KEYS_EXTRA = ("weaknesses",)

BANDS = {
    "content": {
        0: "Content is totally irrelevant. Target reader is not informed.",  # p. 35 (printed 33)
        1: "Irrelevances and misinterpretation of task may be present. Target reader is minimally informed.",  # p. 35 (printed 33)
        2: "Performance shares features of Bands 1 and 3.",  # p. 35 (printed 33)
        3: "Minor irrelevances and/or omissions may be present. Target reader is on the whole informed.",  # p. 35 (printed 33)
        4: "Performance shares features of Bands 3 and 5.",  # p. 35 (printed 33)
        5: "All content is relevant to the task. Target reader is fully informed.",  # p. 35 (printed 33)
    },
    "communicative_achievement": {
        0: "Performance below Band 1.",  # p. 35 (printed 33)
        1: "Uses the conventions of the communicative task in generally appropriate ways to communicate straightforward ideas.",  # p. 35 (printed 33)
        2: "Performance shares features of Bands 1 and 3.",  # p. 35 (printed 33)
        3: "Uses the conventions of the communicative task to hold the target reader’s attention and communicate straightforward ideas.",  # p. 35 (printed 33)
        4: "Performance shares features of Bands 3 and 5.",  # p. 35 (printed 33)
        5: "Uses the conventions of the communicative task effectively to hold the target reader’s attention and communicate straightforward and complex ideas, as appropriate.",  # p. 35 (printed 33)
    },
    "organisation": {
        0: "Performance below Band 1.",  # p. 35 (printed 33)
        1: "Text is connected and coherent, using basic linking words and a limited number of cohesive devices.",  # p. 35 (printed 33)
        2: "Performance shares features of Bands 1 and 3.",  # p. 35 (printed 33)
        3: "Text is generally well organised and coherent, using a variety of linking words and cohesive devices.",  # p. 35 (printed 33)
        4: "Performance shares features of Bands 3 and 5.",  # p. 35 (printed 33)
        5: "Text is well organised and coherent, using a variety of cohesive devices and organisational patterns to generally good effect.",  # p. 35 (printed 33)
    },
    "language": {
        0: "Performance below Band 1.",  # p. 35 (printed 33)
        1: "Uses everyday vocabulary generally appropriately, while occasionally overusing certain lexis. Uses simple grammatical forms with a good degree of control. While errors are noticeable, meaning can still be determined.",  # p. 35 (printed 33)
        2: "Performance shares features of Bands 1 and 3.",  # p. 35 (printed 33)
        3: "Uses a range of everyday vocabulary appropriately, with occasional inappropriate use of less common lexis. Uses a range of simple and some complex grammatical forms with a good degree of control. Errors do not impede communication.",  # p. 35 (printed 33)
        4: "Performance shares features of Bands 3 and 5.",  # p. 35 (printed 33)
        5: "Uses a range of vocabulary, including less common lexis, appropriately. Uses a range of simple and complex grammatical forms with control and flexibility. Occasional errors may be present but do not impede communication.",  # p. 35 (printed 33)
    },
}

RUBRIC_TEXT = """Assessment scales (B2 First Handbook, pages 33-35)
Tasks are marked using assessment scales that were developed with explicit reference to the Common European Framework of Reference (CEFR). The scales consist of four subscales: Content, Communicative Achievement, Organisation, and Language:
• Content focuses on how well the candidate has fulfilled the task, in other words if they have done what they were asked to do.
• Communicative Achievement focuses on how appropriate the writing is for the task and whether the candidate has used the appropriate register.
• Organisation focuses on the way the candidate puts together the piece of writing, in other words if it is logical and ordered.
• Language focuses on vocabulary and grammar. This includes the range of language as well as how accurate it is.
Responses are marked on each subscale from 0 to 5.

B2 WRITING ASSESSMENT SCALE:

[CONTENT]
Band 5: All content is relevant to the task. Target reader is fully informed.
Band 4: Performance shares features of Bands 3 and 5.
Band 3: Minor irrelevances and/or omissions may be present. Target reader is on the whole informed.
Band 2: Performance shares features of Bands 1 and 3.
Band 1: Irrelevances and misinterpretation of task may be present. Target reader is minimally informed.
Band 0: Content is totally irrelevant. Target reader is not informed.

[COMMUNICATIVE ACHIEVEMENT]
Band 5: Uses the conventions of the communicative task effectively to hold the target reader’s attention and communicate straightforward and complex ideas, as appropriate.
Band 4: Performance shares features of Bands 3 and 5.
Band 3: Uses the conventions of the communicative task to hold the target reader’s attention and communicate straightforward ideas.
Band 2: Performance shares features of Bands 1 and 3.
Band 1: Uses the conventions of the communicative task in generally appropriate ways to communicate straightforward ideas.
Band 0: Performance below Band 1.

[ORGANISATION]
Band 5: Text is well organised and coherent, using a variety of cohesive devices and organisational patterns to generally good effect.
Band 4: Performance shares features of Bands 3 and 5.
Band 3: Text is generally well organised and coherent, using a variety of linking words and cohesive devices.
Band 2: Performance shares features of Bands 1 and 3.
Band 1: Text is connected and coherent, using basic linking words and a limited number of cohesive devices.
Band 0: Performance below Band 1.

[LANGUAGE]
Band 5: Uses a range of vocabulary, including less common lexis, appropriately. Uses a range of simple and complex grammatical forms with control and flexibility. Occasional errors may be present but do not impede communication.
Band 4: Performance shares features of Bands 3 and 5.
Band 3: Uses a range of everyday vocabulary appropriately, with occasional inappropriate use of less common lexis. Uses a range of simple and some complex grammatical forms with a good degree of control. Errors do not impede communication.
Band 2: Performance shares features of Bands 1 and 3.
Band 1: Uses everyday vocabulary generally appropriately, while occasionally overusing certain lexis. Uses simple grammatical forms with a good degree of control. While errors are noticeable, meaning can still be determined.
Band 0: Performance below Band 1."""

WRITING_SYSTEM = f"""You are a senior official Cambridge Assessment English examiner for the B2 First (FCE) exam.
Your task is to assess Writing texts by strictly applying the official Cambridge scale included below:

{RUBRIC_TEXT}

MANDATORY MARKING RULES:
1. Return ONLY a valid JSON object, no markdown blocks (no ```json), no preamble and no extra text.
2. Assess the 4 official criteria: "content", "communicative_achievement", "organisation", "language".
3. Assign integer scores from 0 to 5 in "bands" for each criterion according to the official descriptors.
4. In "quotes", include for each criterion an exact verbatim quote taken from the student's text (in English) that justifies the assigned band. If there is no valid quote from the student's text, the band is invalid.
5. In "feedback", write the explanatory feedback for the student in clear English; keep quotes and English corrections in English.
6. In "rewrite", return exactly 3 strings: 3 sentences from the student's own text rewritten and improved in English at B2+/C1 level (do not invent new text unrelated to the student's writing).
7. Do not invent grammatical rules or descriptors that are not in the official rubric.

CALIBRATION RULES (mandatory):
1. Be strict. Band 5 means performance at the top of B2 / start of C1. Most real B2
   candidates land in 3-4, and a typical school essay is 3.
2. Before assigning any band, silently list at least 2 concrete weaknesses of the text
   for EACH criterion. If you can name 2 weaknesses in a criterion, that criterion
   CANNOT be 5.
3. For every criterion you score 4 or 5, state in the feedback WHY IT IS NOT ONE BAND HIGHER.
   This justification is mandatory and goes in the feedback text.
4. Band 5 on 'language' requires: a wide range of structures (conditionals, passives,
   relative clauses, perfect tenses) AND no more than one minor slip.
   Simple but correct sentences = 3, not 5.
5. Band 5 on 'organisation' requires: clear paragraphing with a developed argument in
   each paragraph AND a range of linking devices. A list of 'Firstly/Secondly' with
   one sentence each = 3.
6. Do not reward effort, length or neatness. Only observable features in the rubric.
7. If the text is under 120 words for a Part 1 task (140-190 expected), 'content'
   cannot exceed 3.

Return ONLY this exact JSON shape (no markdown, no extra text):
{{"bands":{{"content":N,"communicative_achievement":N,"organisation":N,"language":N}},
 "feedback":{{"content":"...","communicative_achievement":"...","organisation":"...","language":"..."}},
 "quotes":{{"content":"...","communicative_achievement":"...","organisation":"...","language":"..."}},
 "weaknesses":{{"content":["...","..."],"communicative_achievement":["...","..."],
               "organisation":["...","..."],"language":["...","..."]}},
 "rewrite":["...","...","..."]}}
N is an integer 0-5. feedback, quotes and weaknesses are OBJECTS with exactly those 4 keys.
Each value in weaknesses is an ARRAY of at least 2 non-empty strings (concrete weaknesses).
rewrite is an ARRAY of exactly 3 strings. Never return arrays where objects are required."""


def writing_prompt(text, kind):
    """Build the full prompt to assess a Writing task of type `kind`."""
    return (
        f"{WRITING_SYSTEM}\n\n"
        f"=== TASK TYPE (GENRE) ===\n{kind}\n\n"
        f"=== STUDENT TEXT ===\n{text}\n\n"
        f"Return only the JSON with the keys bands, feedback, quotes, weaknesses and rewrite."
    )
