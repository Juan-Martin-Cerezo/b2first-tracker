#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Semantic validation and in-memory micro-scoring for Speaking v3.

All transcripts are processed strictly in memory and discarded immediately
after validation and micro-scoring; nothing text-shaped from the candidate is
ever persisted or returned to the client.
"""
import re

# ---------------------------------------------------------------------------
# Non-English / Spanish detection
# ---------------------------------------------------------------------------
_SPANISH_MARKERS = frozenset({
    "hola", "buenos", "buenas", "dias", "días", "tardes", "noches",
    "gracias", "por", "favor", "porque", "pero", "también", "tambien",
    "creo", "pienso", "quiero", "tengo", "estoy", "soy", "vivo",
    "llamo", "nombre", "ciudad", "pais", "país", "casa", "trabajo",
    "escuela", "amigos", "familia", "tiempo", "mejor", "peor", "mucho",
    "mucha", "muchos", "muchas", "muy", "como", "cómo", "donde", "dónde",
    "cuando", "cuándo", "qué", "que", "para", "con", "sobre", "entre",
    "esta", "está", "esto", "este", "ese", "esa", "eso", "unos", "unas",
    "los", "las", "del", "una", "la", "el", "en", "mi", "mis",
    "gusta", "gustan", "encanta", "prefiero", "hacer", "ver", "comer",
    "dormir", "viajar", "viaje", "vacaciones", "fotos", "foto", "personas",
    "gente", "parque", "playa", "español", "espanol", "inglés", "ingles",
    "siempre", "nunca", "ahora", "después", "despues", "antes", "entonces",
    "además", "ademas", "aunque", "puedo", "puede", "puedes", "debe",
    "hay", "fue", "tiene", "tienes", "hace", "dice", "decir", "hablar",
    "hablo", "entiendo", "pregunta", "respuesta", "estudiar", "aprender",
    "película", "pelicula", "comida", "deporte", "deportes", "música",
    "musica", "clases", "estudiantes", "profesores", "turistas", "primera",
    "segunda", "mientras", "aquí", "aqui", "allí", "alli", "todo", "toda",
    "todos", "todas", "nada", "algo", "alguien", "nadie", "sí", "claro",
    "bueno", "bien", "mal", "grande", "pequeño", "pequeno", "nuevo",
    "nueva", "viejo", "vieja", "fácil", "facil", "difícil", "dificil",
    "divertido", "aburrido", "perdón", "perdon", "disculpa", "adiós",
    "adios", "mañana", "manana", "ayer", "hoy", "semana", "nosotros",
    "ellos", "ellas", "usted", "ustedes",
    "bonjour", "merci", "salut", "parce", "mais", "avec", "pour",
    "hallo", "danke", "ich", "nicht", "aber", "oder", "sehr",
    "ciao", "grazie", "perche", "perché", "molto", "sono", "voglio",
    "olá", "obrigado", "obrigada", "você", "voce", "muito", "não", "nao",
})

_NON_EN_CHARS_RE = re.compile(r"[¿¡ñÑçÇß]")

_ENGLISH_COMMON = frozenset({
    "the", "and", "that", "this", "with", "from", "have", "for", "are",
    "was", "were", "been", "not", "but", "they", "you", "your", "our",
    "my", "name", "live", "from", "like", "think", "because", "would",
    "could", "should", "about", "very", "more", "most", "really", "also",
    "both", "whereas", "while", "first", "second", "picture", "photo",
    "photograph", "people", "friends", "family", "time", "good", "better",
    "prefer", "agree", "disagree", "important", "different", "usually",
})


def is_non_english(text, allow_proper_nouns_only=False):
    """Return True if `text` is clearly Spanish or another non-English language.

    When `allow_proper_nouns_only=True` (used for name and home steps), bare
    proper nouns like 'Juan', 'María', 'Córdoba', 'Buenos Aires', 'São Paulo'
    are NOT flagged as non-English.
    """
    s = str(text or "").strip()
    if not s:
        return False
    tokens = re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑüÜçÇàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛãõÃÕ]+", s)
    if not tokens:
        return False
    low = [t.lower() for t in tokens]

    if _NON_EN_CHARS_RE.search(s):
        # Allow a single proper name with ñ/ç only on name/home steps (e.g. "Iñaki", "Peña")
        if allow_proper_nouns_only and len(low) <= 3 and not any(w in _SPANISH_MARKERS for w in low):
            return False
        return True

    sp_hits = sum(1 for w in low if w in _SPANISH_MARKERS)
    en_hits = sum(1 for w in low if w in _ENGLISH_COMMON)

    if allow_proper_nouns_only:
        # "Me llamo Juan" / "Vivo en Madrid" -> non-English!
        # "Buenos Aires" -> "buenos" is 1 hit, "aires" is 0; don't flag city names!
        if sp_hits >= 2 and en_hits == 0:
            return True
        if len(low) >= 2 and low[0] in ("me", "vivo", "soy", "hola", "mi", "yo") and sp_hits >= 1:
            return True
        return False

    if sp_hits >= 2 and sp_hits > en_hits:
        return True
    if len(low) <= 3 and sp_hits >= 1 and en_hits == 0:
        return True
    return False


# ---------------------------------------------------------------------------
# Intro: Name validation
# ---------------------------------------------------------------------------
_NAME_PREFIX_RE = re.compile(
    r"^(?:(?:hello|good\s+(?:morning|afternoon|evening))[,.!]?\s+)?"
    r"(?:my\s+name(?:'s|\s+is)|i(?:'m|\s+am)|it(?:'s|\s+is)|call\s+me)\s+",
    re.IGNORECASE,
)

_NON_NAME_WORDS = frozenset({
    "yes", "no", "yeah", "nope", "hello", "hi", "hey", "good", "morning",
    "afternoon", "evening", "fine", "thanks", "thank", "you", "please",
    "sorry", "what", "where", "when", "why", "how", "who", "maybe",
    "nothing", "something", "anything", "everything", "pizza", "pasta",
    "football", "tennis", "music", "film", "movie", "book", "books",
    "coffee", "tea", "water", "dog", "cat", "car", "house", "school",
    "work", "study", "like", "love", "hate", "enjoy", "prefer", "want",
    "live", "from", "years", "old", "twenty", "thirty", "eighteen",
    "seventeen", "sixteen", "nineteen", "fifteen", "student", "teacher",
    "engineer", "doctor", "happy", "tired", "ready", "sure", "okay", "ok",
    "banana", "bananas", "apple", "elephant", "purple", "blue", "red",
    "green", "weather", "sunny", "raining", "monday", "tuesday", "today",
    "tomorrow", "yesterday", "test", "exam", "english", "spanish",
})

_NON_NAME_VERB_RE = re.compile(
    r"\b(?:like|love|hate|eat|eating|play|playing|watch|watching|live|living|"
    r"work|working|study|studying|go|going|want|need|have|has|had|think|"
    r"prefer|enjoy|cook|cooking|drink|drinking|sleep|sleeping|read|reading)\b",
    re.IGNORECASE,
)


def validate_name(text):
    """Validate candidate's spoken name.

    Returns ``(ok, clean_name, reason)`` where reason is one of:
    ``"ok"``, ``"silence"``, ``"non_english"``, ``"invalid_name"``.
    """
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return False, "", "silence"
    if is_non_english(s, allow_proper_nouns_only=True):
        return False, "", "non_english"

    cleaned = s.strip(" .,!?;:\"'")
    # Reject sentences containing action verbs like "I like pizza"
    if _NON_NAME_VERB_RE.search(cleaned):
        return False, "", "invalid_name"

    m = _NAME_PREFIX_RE.match(cleaned)
    if m:
        rest = cleaned[m.end():].strip(" .,!?;:\"'")
    else:
        rest = cleaned

    # Strip trailing polite filler like "please" / "nice to meet you"
    rest = re.split(r"[,.!?]|\bnice\s+to\s+meet\b|\band\s+i\b", rest, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    words = [w for w in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'-]+", rest) if w]
    if not words or len(words) > 4:
        return False, "", "invalid_name"

    # Every word must be plausible as part of a person's name (not digits, not common non-name words)
    if any(w.lower() in _NON_NAME_WORDS for w in words):
        return False, "", "invalid_name"
    if any(len(w) < 2 for w in words):
        return False, "", "invalid_name"

    first_name = words[0].capitalize()
    return True, first_name, "ok"


# ---------------------------------------------------------------------------
# Intro: Home (city / country / area) validation
# ---------------------------------------------------------------------------
_HOME_PREFIX_RE = re.compile(
    r"^(?:(?:i\s+live|i(?:'m|\s+am)\s+living|i(?:'m|\s+am)|i\s+come)\s+)?"
    r"(?:(?:in|from|near|outside|just\s+outside)\s+)?"
    r"(?:(?:the\s+(?:north|south|east|west|centre|center|capital|city|town|suburbs)\s+of)\s+)?",
    re.IGNORECASE,
)

_NON_HOME_WORDS = frozenset({
    "yes", "no", "yeah", "nope", "hello", "hi", "hey", "good", "morning",
    "afternoon", "evening", "pizza", "pasta", "football", "tennis", "music",
    "film", "movie", "book", "books", "coffee", "tea", "water", "dog", "cat",
    "cooking", "reading", "swimming", "running", "sleeping", "watching",
    "nothing", "maybe", "fine", "thanks", "please", "sorry", "happy",
    "tired", "hungry", "banana", "bananas", "elephant", "elephants",
    "purple", "yellow", "blue", "red", "monday", "tuesday", "friday",
    "sunday", "yesterday", "tomorrow", "exam", "test",
})

_NON_HOME_SENTENCE_RE = re.compile(
    r"\b(?:my\s+name\s+is|i\s+like|i\s+love|i\s+hate|i\s+enjoy|i\s+prefer|"
    r"i\s+want|i\s+don['’]?t\s+know|i\s+eat|i\s+play|i\s+watch)\b",
    re.IGNORECASE,
)


def validate_home(text):
    """Validate candidate's answer to 'Where do you live?'.

    Accepts city, country, region, or area ('Buenos Aires', 'I live in Buenos
    Aires', 'I'm from Argentina', 'In the north of Spain', etc.).
    Returns ``(ok, clean_home, reason)``.
    """
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return False, "", "silence"
    if is_non_english(s, allow_proper_nouns_only=True):
        return False, "", "non_english"

    cleaned = s.strip(" .,!?;:\"'")
    if _NON_HOME_SENTENCE_RE.search(cleaned):
        return False, "", "invalid_home"

    has_place_cue = bool(re.search(
        r"\b(?:live\s+in|living\s+in|from|near|city|town|village|country|"
        r"capital|suburb|suburbs|district|province|region|north|south|east|west|coast)\b",
        cleaned, re.IGNORECASE,
    ))

    m = _HOME_PREFIX_RE.match(cleaned)
    rest = cleaned[m.end():].strip(" .,!?;:\"'") if m else cleaned
    # Trim explanatory clause after "which is", "it's", "because"
    rest = re.split(r"\b(?:which\s+is|it(?:'s|\s+is)|because|for\s+\d+)\b", rest, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,.")

    words = [w for w in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'-]+", rest) if w]
    if not words:
        return False, "", "invalid_home"
    if not has_place_cue and len(words) > 5:
        return False, "", "invalid_home"
    if len(words) > 10:
        return False, "", "invalid_home"

    non_stop = [w.lower() for w in words if w.lower() not in ("the", "of", "in", "a", "an", "near", "city", "town")]
    if not non_stop:
        return False, "", "invalid_home"
    if all(w in _NON_HOME_WORDS for w in non_stop):
        return False, "", "invalid_home"
    if not has_place_cue and any(w in _NON_HOME_WORDS for w in non_stop):
        return False, "", "invalid_home"

    place = " ".join(words[:5])
    return True, place, "ok"


# ---------------------------------------------------------------------------
# General Topic / Question Relevance Validation (Parts 1, 2-followup, 3, 4)
# ---------------------------------------------------------------------------
_STOPWORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "its", "may", "new", "now", "old", "see", "two", "way", "who",
    "boy", "did", "let", "put", "say", "she", "too", "use", "that", "this",
    "with", "from", "they", "them", "been", "have", "what", "when", "where",
    "which", "their", "there", "these", "those", "would", "could", "should",
    "about", "into", "more", "some", "such", "than", "then", "very", "just",
    "also", "much", "many", "really", "quite", "well", "actually", "maybe",
    "perhaps", "because", "since", "although", "though", "however", "rather",
    "your", "yours", "mine", "myself", "does", "don", "didn", "won", "isn",
    "aren", "wasn", "weren", "haven", "hasn", "going", "thing", "things",
    "like", "love", "tell", "know", "think", "make", "take", "give", "want",
    "need", "feel", "look", "good", "best", "ever", "something", "anything",
    "nothing", "people", "person", "spend",
})

_BLATANT_NONSENSE_RE = re.compile(
    r"\b(?:pizza|bananas?|elephants?|purple\s+monkey|two\s+plus\s+two|"
    r"lorem\s+ipsum|asdf|blah\s+blah|testing\s+one\s+two)\b",
    re.IGNORECASE,
)

# Domain-general stance / elaboration words that legitimate B2 answers use
_CONVERSATION_CUES = frozenset({
    "prefer", "enjoy", "think", "believe", "agree", "disagree", "depends",
    "usually", "normally", "sometimes", "often", "rarely", "never", "always",
    "important", "useful", "helpful", "interesting", "difficult", "easier",
    "easiest", "better", "best", "worse", "advantage", "disadvantage",
    "expensive", "cheap", "healthy", "relax", "relaxing", "fun", "popular",
    "opinion", "reason", "example", "especially", "personally", "definitely",
    "probably", "suppose", "first", "second", "both", "either", "neither",
    "sure", "true", "right", "point", "idea", "ideas", "option", "options",
    "choice", "choose", "pick", "decide", "sensible", "practical", "maybe",
    "perhaps", "actually", "honestly", "fair", "sense", "totally", "partly",
    "completely", "convinced", "view", "perspective", "however", "whereas",
    "although", "though", "because", "would", "could", "might", "should",
})

_COOPERATIVE_RE = re.compile(
    r"\b(?:"
    r"i\s+(?:totally\s+|completely\s+|partly\s+|really\s+|quite\s+|don['’]?t\s+)?agree"
    r"|i\s+(?:partly\s+|totally\s+)?disagree"
    r"|that['’]?s\s+(?:true|right|fair|a\s+(?:good|fair|great)\s+point|interesting|sensible)"
    r"|that\s+is\s+(?:true|right|fair|a\s+(?:good|fair|great)\s+point)"
    r"|i['’]?m\s+not\s+(?:really\s+|completely\s+|entirely\s+)?sure"
    r"|i\s+am\s+not\s+(?:really\s+|completely\s+)?sure"
    r"|not\s+(?:really|sure|necessarily|always|quite)"
    r"|i\s+(?:don['’]?t\s+)?think\s+so"
    r"|i\s+see\s+(?:your\s+point|what\s+you\s+mean)"
    r"|you['’]?re\s+(?:probably\s+)?right|you\s+are\s+right"
    r"|you['’]?ve\s+got\s+a\s+point|good\s+point|fair\s+point|fair\s+enough"
    r"|it\s+depends|that\s+makes\s+sense|makes\s+sense"
    r"|what\s+do\s+you\s+think|how\s+about|what\s+about"
    r"|shall\s+we\s+(?:move\s+on|look\s+at|talk\s+about|choose|pick|go\s+with)"
    r"|let['’]?s\s+(?:move\s+on|talk\s+about|choose|go\s+with)"
    r"|yes\s*,?\s*(?:definitely|exactly|absolutely|i\s+do|i\s+would|probably|true|sure)"
    r"|no\s*,?\s*(?:not\s+really|i\s+don['’]?t|i\s+wouldn['’]?t)"
    r"|in\s+my\s+(?:opinion|view)|to\s+be\s+honest|on\s+the\s+other\s+hand"
    r")\b",
    re.IGNORECASE,
)

_PART3_META_START_RE = re.compile(
    r"^(?:(?:excuse\s+me|sorry|well|um|uh|so|hey)[,.]?\s+)?"
    r"(?:"
    r"(?:can|could|may|shall)\s+i\s+(?:start|begin|go\s+first)"
    r"|do\s+you\s+mind\s+if\s+i\s+(?:start|begin|go\s+first)"
    r"|mind\s+if\s+i\s+(?:start|begin|go\s+first)"
    r"|would\s+you\s+like\s+me\s+to\s+(?:start|begin|go\s+first)"
    r"|i(?:'ll|\s+will|\s+can)\s+(?:start|begin|go\s+first)"
    r"|let\s+me\s+(?:start|begin|go\s+first)"
    r")"
    r"(?:\s+(?:first|off|now|please))?[\s?!.,]*$",
    re.IGNORECASE,
)


def is_part3_meta_start(text):
    """Return True if candidate is asking/offering to start Part 3 ('Can I start?', 'Shall I start?', 'I'll start')."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return False
    words = re.findall(r"[a-zA-Z']+", s)
    if len(words) > 9:
        return False
    return bool(_PART3_META_START_RE.match(s))


def detect_mentioned_options(text, options):
    """Return options from `options` whose content words appear in `text` (in-memory only)."""
    s = str(text or "").lower()
    if not s or not options:
        return []
    words = [w.strip("'") for w in re.findall(r"[a-z']+", s) if len(w.strip("'")) >= 3 and w.strip("'") not in _STOPWORDS]
    if not words:
        return []
    matched = []
    for opt in options:
        opt_toks = [
            tok for tok in re.findall(r"[a-z]+", str(opt or "").lower())
            if len(tok) >= 3 and tok not in _STOPWORDS
        ]
        if any(_stem_match(w, ot) for w in words for ot in opt_toks):
            matched.append(opt)
    return matched


def _stem_match(a, b):
    if a == b:
        return True
    s, l = (a, b) if len(a) <= len(b) else (b, a)
    if len(s) >= 4 and l.startswith(s) and len(l) - len(s) <= 4:
        return True
    if len(s) >= 4 and s.endswith("e") and l.startswith(s[:-1]) and len(l) - len(s) <= 3:
        return True
    if len(s) >= 4 and s.endswith("y") and l.startswith(s[:-1]) and l[len(s) - 1:] in ("ies", "ied", "ier", "iest", "ily"):
        return True
    return False


def validate_topic_answer(text, question_text="", topic="", keywords=None, part=1, allow_cooperative=False):
    """Validate an answer in Part 1, Part 2 follow-up, Part 3, or Part 4.

    Returns ``(ok, reason)`` where reason is one of:
    ``"ok"``, ``"silence"``, ``"non_english"``, ``"off_topic"``.
    """
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return False, "silence"
    if is_non_english(s, allow_proper_nouns_only=False):
        return False, "non_english"

    words = re.findall(r"[a-zA-Z']+", s.lower())
    interactive_part = (part in (3, 4)) or bool(allow_cooperative)

    if len(words) < 2:
        # In Part 3/4, allow single-word cooperative markers only if unambiguous?
        # Keep minimum 2 words (e.g. "I agree", "Not sure", "That's true") so accidental noise is rejected.
        return False, "off_topic"

    # Build expected semantic field from keywords + question + topic
    expected = set()
    for kw in (keywords or []):
        for tok in re.findall(r"[a-z]+", str(kw).lower()):
            if len(tok) >= 3:
                expected.add(tok)
    for src in (question_text, topic):
        for tok in re.findall(r"[a-z]+", str(src or "").lower()):
            if len(tok) >= 4 and tok not in _STOPWORDS:
                expected.add(tok)

    # Check if blatant off-topic joke/filler appears when NOT in expected keywords
    if _BLATANT_NONSENSE_RE.search(s):
        hit_nonsense = any(
            m.group(0).lower() in expected
            for m in _BLATANT_NONSENSE_RE.finditer(s)
        )
        if not hit_nonsense:
            # Allow pizza ONLY if the question/topic itself is actually about cooking/food
            if not re.search(r"\b(?:cook|cooking|food|meal|eat|dish)\b", f"{question_text} {topic}", re.IGNORECASE):
                return False, "off_topic"

    # In Part 3 and Part 4, cooperative short reactions ("I agree", "That's true",
    # "I'm not sure", "Good point") are legitimate interactive turns!
    if interactive_part and _COOPERATIVE_RE.search(s):
        return True, "ok"

    # Check overlap with expected keywords
    content_words = [w.strip("'") for w in words if len(w.strip("'")) >= 3 and w.strip("'") not in _STOPWORDS]
    topic_hit = any(
        _stem_match(cw, ek)
        for cw in content_words
        for ek in expected
    )
    if topic_hit:
        return True, "ok"

    # In Part 3/4, accept reasonable opinion/reaction statements that express a stance
    # without demanding exact card keywords.
    stance_hits = sum(
        1 for w in words
        if w in _CONVERSATION_CUES or w in ("because", "since", "although", "while", "whereas", "would", "could", "might", "yes", "no")
    )
    if interactive_part and stance_hits >= 1 and len(words) >= 3:
        return True, "ok"

    # For very short answers without any topic hit, reject as off-topic
    if len(words) < 5:
        return False, "off_topic"

    # If answer is longer (>= 8 words) with clear conversational stance, accept paraphrased answers.
    if stance_hits >= 2 and len(words) >= 8:
        return True, "ok"

    return False, "off_topic"


# ---------------------------------------------------------------------------
# Part 2: Photo comparison check (NEVER rejects long turn for off-topic!)
# ---------------------------------------------------------------------------
_COMPARE_MARKERS = (
    r"\bboth\b",
    r"\bwhereas\b",
    r"\bwhile\b",
    r"\bwhilst\b",
    r"\bin\s+contrast\b",
    r"\bby\s+contrast\b",
    r"\bon\s+the\s+other\s+hand\b",
    r"\bhowever\b",
    r"\bunlike\b",
    r"\bsimilar(?:ly)?\b",
    r"\bdifferen(?:t|ce|tly)\b",
    r"\bcompar(?:e|ing|ed|ison)\b",
    r"\bfirst\b.*\bsecond\b",
    r"\bsecond\b.*\bfirst\b",
    r"\bone\s+(?:photo|photograph|picture)\b.*\bother\b",
    r"\bmore\s+\w+\s+than\b",
    r"\bless\s+\w+\s+than\b",
)
_COMPARE_RES = [re.compile(p, re.IGNORECASE) for p in _COMPARE_MARKERS]


def did_compare_photos(text):
    """Return True if the candidate's Part 2 long turn compared both photographs."""
    s = str(text or "")
    return any(rx.search(s) for rx in _COMPARE_RES)


# ---------------------------------------------------------------------------
# In-memory numeric micro-scoring (discards transcript immediately)
# ---------------------------------------------------------------------------
_CONNECTIVES = frozenset({
    "because", "although", "though", "however", "whereas", "while", "whilst",
    "moreover", "furthermore", "besides", "therefore", "consequently",
    "instead", "otherwise", "unless", "whenever", "meanwhile", "finally",
    "firstly", "secondly", "overall", "personally", "especially", "actually",
})

_INTERACTIVE_CUES = frozenset({
    "agree", "disagree", "think", "opinion", "point", "right", "true",
    "suppose", "perhaps", "maybe", "suggest", "choose", "decide", "shall",
    "what", "how", "would", "could",
})


def micro_score_turn(text, accepted=True, part=1, compared_photos=None):
    """Compute numeric micro-scores (0.0-5.0) for one candidate turn in memory.

    Returns ONLY numbers — never raw words or transcripts.
    """
    words = re.findall(r"[a-zA-Z']+", str(text or "").lower())
    wc = len(words)
    if wc == 0:
        return {"gv": 0.0, "dm": 0.0, "ic": 0.0, "word_count": 0}

    unique_ratio = len(set(words)) / float(wc)
    long_words = sum(1 for w in words if len(w) >= 7)
    conn_count = sum(1 for w in words if w in _CONNECTIVES)
    inter_count = sum(1 for w in words if w in _INTERACTIVE_CUES) + (1 if "?" in str(text) else 0)

    # Grammar & Vocabulary (0-5)
    gv = 2.0
    if wc >= 8:
        gv += 0.6
    if wc >= 18:
        gv += 0.5
    if unique_ratio >= 0.65:
        gv += 0.5
    if long_words >= 2:
        gv += 0.5
    if long_words >= 5:
        gv += 0.4
    if not accepted:
        gv -= 1.0

    # Discourse Management (0-5)
    dm = 2.0
    if wc >= 10:
        dm += 0.6
    if wc >= 25:
        dm += 0.5
    if conn_count >= 1:
        dm += 0.7
    if conn_count >= 2:
        dm += 0.6
    if compared_photos is True:
        dm += 0.4
    elif compared_photos is False:
        dm -= 0.7
    if not accepted:
        dm -= 1.0

    # Interactive Communication (0-5)
    ic = 2.2
    if accepted:
        ic += 0.8
    else:
        ic -= 1.2
    if wc >= 6:
        ic += 0.4
    if inter_count >= 1:
        ic += 0.6
    if inter_count >= 2:
        ic += 0.5
    if part in (3, 4) and "?" in str(text):
        ic += 0.4

    def _clamp(v):
        return round(max(0.0, min(5.0, v)), 2)

    return {
        "gv": _clamp(gv),
        "dm": _clamp(dm),
        "ic": _clamp(ic),
        "word_count": wc,
    }
