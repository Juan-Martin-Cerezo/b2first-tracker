# -*- coding: utf-8 -*-
"""Rúbrica oficial de Writing de B2 First (Cambridge) y prompts del corrector IA.

Fuente: /home/juan/Descargas/b2-first/05-Handbooks/b2-first-handbook.pdf
Páginas del PDF: 33–36 (numeración impresa: 31–34).
"""

RUBRIC_SOURCE = "B2 First Handbook, páginas 32-35 (Cambridge University Press)"

SCHEMA_KEYS = ("content", "communicative_achievement", "organisation", "language")

BANDS = {
    "content": {
        0: "Content is totally irrelevant. Target reader is not informed.",  # pág 35 (impreso 33)
        1: "Irrelevances and misinterpretation of task may be present. Target reader is minimally informed.",  # pág 35 (impreso 33)
        2: "Performance shares features of Bands 1 and 3.",  # pág 35 (impreso 33)
        3: "Minor irrelevances and/or omissions may be present. Target reader is on the whole informed.",  # pág 35 (impreso 33)
        4: "Performance shares features of Bands 3 and 5.",  # pág 35 (impreso 33)
        5: "All content is relevant to the task. Target reader is fully informed.",  # pág 35 (impreso 33)
    },
    "communicative_achievement": {
        0: "Performance below Band 1.",  # pág 35 (impreso 33)
        1: "Uses the conventions of the communicative task in generally appropriate ways to communicate straightforward ideas.",  # pág 35 (impreso 33)
        2: "Performance shares features of Bands 1 and 3.",  # pág 35 (impreso 33)
        3: "Uses the conventions of the communicative task to hold the target reader’s attention and communicate straightforward ideas.",  # pág 35 (impreso 33)
        4: "Performance shares features of Bands 3 and 5.",  # pág 35 (impreso 33)
        5: "Uses the conventions of the communicative task effectively to hold the target reader’s attention and communicate straightforward and complex ideas, as appropriate.",  # pág 35 (impreso 33)
    },
    "organisation": {
        0: "Performance below Band 1.",  # pág 35 (impreso 33)
        1: "Text is connected and coherent, using basic linking words and a limited number of cohesive devices.",  # pág 35 (impreso 33)
        2: "Performance shares features of Bands 1 and 3.",  # pág 35 (impreso 33)
        3: "Text is generally well organised and coherent, using a variety of linking words and cohesive devices.",  # pág 35 (impreso 33)
        4: "Performance shares features of Bands 3 and 5.",  # pág 35 (impreso 33)
        5: "Text is well organised and coherent, using a variety of cohesive devices and organisational patterns to generally good effect.",  # pág 35 (impreso 33)
    },
    "language": {
        0: "Performance below Band 1.",  # pág 35 (impreso 33)
        1: "Uses everyday vocabulary generally appropriately, while occasionally overusing certain lexis. Uses simple grammatical forms with a good degree of control. While errors are noticeable, meaning can still be determined.",  # pág 35 (impreso 33)
        2: "Performance shares features of Bands 1 and 3.",  # pág 35 (impreso 33)
        3: "Uses a range of everyday vocabulary appropriately, with occasional inappropriate use of less common lexis. Uses a range of simple and some complex grammatical forms with a good degree of control. Errors do not impede communication.",  # pág 35 (impreso 33)
        4: "Performance shares features of Bands 3 and 5.",  # pág 35 (impreso 33)
        5: "Uses a range of vocabulary, including less common lexis, appropriately. Uses a range of simple and complex grammatical forms with control and flexibility. Occasional errors may be present but do not impede communication.",  # pág 35 (impreso 33)
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

WRITING_SYSTEM = f"""Sos un examinador senior oficial de Cambridge Assessment English para el examen B2 First (FCE).
Tu tarea es evaluar textos de Writing aplicando estrictamente la escala oficial de Cambridge que se incluye a continuación:

{RUBRIC_TEXT}

REGLAS OBLIGATORIAS DE CORRECCIÓN:
1. Devolvé SÓLO un objeto JSON válido, sin bloques markdown (sin ```json), sin preámbulos ni texto extra.
2. Evaluá los 4 criterios oficiales: "content", "communicative_achievement", "organisation", "language".
3. Asigná notas enteras de 0 a 5 en "bands" para cada criterio según los descriptores oficiales.
4. En "quotes", incluí para cada criterio una cita textual exacta extraída del texto del alumno (en inglés) que justifique la banda asignada. Si no hay cita válida del texto del alumno, la banda es inválida.
5. En "feedback", redactá la devolución explicativa para el alumno en español rioplatense (vos, tenés, fijate, usaste), manteniendo las citas y las correcciones de inglés en inglés.
6. En "rewrite", devolvé exactamente 3 strings: 3 oraciones del propio texto del alumno reescritas y mejoradas en inglés a nivel B2+/C1 (no inventes texto nuevo ajeno al escrito del alumno).
7. Prohibido inventar reglas gramaticales o descriptores que no estén en la rúbrica oficial.

Return ONLY this exact JSON shape (no markdown, no extra text):
{{"bands":{{"content":N,"communicative_achievement":N,"organisation":N,"language":N}},
 "feedback":{{"content":"...","communicative_achievement":"...","organisation":"...","language":"..."}},
 "quotes":{{"content":"...","communicative_achievement":"...","organisation":"...","language":"..."}},
 "rewrite":["...","...","..."]}}
N is an integer 0-5. feedback and quotes are OBJECTS with exactly those 4 keys.
rewrite is an ARRAY of exactly 3 strings. Never return arrays where objects are required."""


def writing_prompt(text, kind):
    """Construye el prompt completo para evaluar un Writing de tipo `kind`."""
    return (
        f"{WRITING_SYSTEM}\n\n"
        f"=== TIPO DE TAREA (GENRE) ===\n{kind}\n\n"
        f"=== TEXTO DEL ALUMNO ===\n{text}\n\n"
        f"Devolvé únicamente el JSON con las claves bands, feedback, quotes y rewrite."
    )
