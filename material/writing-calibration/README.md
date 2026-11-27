# Writing calibration fixtures

The five `case1..case5` essays and their expected bands were supplied by Juan on 2026-11-27 as the
exact inputs of an external calibration run of this corrector. They are synthetic practice essays
on a single B2 First Part 1 task; they are not official Cambridge answers and carry no copyright
claim. Do not edit them: the whole point is to re-run the same inputs.

`case6_off_topic_c1.txt` (fluent C1 English answering a completely different question on school
sport) and `case7_300_words.txt` (300+ words, correct English, padded and repetitive) are synthetic
practice essays added in Phase WRCAL-1 to cover off-topic and over-long edge cases. Like cases 1–5,
they are synthetic practice essays, not official Cambridge answers.

`expected.json` holds the target bands and the discriminating `must` conditions; it is data for
`tools/calibration_report.py`, never shown to the model.
