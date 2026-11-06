"""Phase 85: every dictionary key must still be referenced somewhere.

The I18N dictionaries only make sense while the markup and the JS use their
keys. This suite extracts both dictionaries from index.html and fails when a
key has no reference left: no data-i18n* attribute, no t('...') call, no entry
in a data table (keys are also passed to t() through variables such as
t(p.key), t(info.name) or t(st.badge)) and no object key.

Keys that are assembled at runtime cannot appear literally in the source, so
they are listed in RUNTIME_KEYS together with the prefix that builds them. The
test checks that the prefix really exists as a concatenation in the code, and
that the list does not grow past the justified size.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "index.html")

# Keys built by concatenation. The value is the literal prefix used by the JS:
# every entry is verified against the source, so a key added without a real
# 'prefix' + variable fails the test instead of silently passing.
RUNTIME_KEYS = {
    "practice_kind_free": "practice_kind_",      # t('practice_kind_' + source.kind)
    "practice_kind_freemium": "practice_kind_",
    "practice_kind_paid": "practice_kind_",
    "sync_ok": "sync_",                          # t('sync_' + state)
    "sync_local": "sync_",
    "sync_off": "sync_",
    "sync_invalid": "sync_",
    "ob_type_w": "ob_type_",                     # t('ob_type_' + skill) in obSkillName()
    "ob_type_l": "ob_type_",
    "ob_type_sp": "ob_type_",
    "ai_state_loading": "ai_state_",             # t('ai_state_' + state)
    "ai_state_ok": "ai_state_",
    "ai_state_error": "ai_state_",
    "spx_brief_part2": "spx_brief_part",         # t('spx_brief_part' + SP_EXAM.part)
    "spx_brief_part3": "spx_brief_part",
    "spx_brief_part4": "spx_brief_part",
    "plan_reset_field_rotationMode": "plan_reset_field_",   # t('plan_reset_field_' + field)
    "plan_reset_field_rueCycle": "plan_reset_field_",
    "plan_reset_field_wCycle": "plan_reset_field_",
    "plan_reset_field_lCycle": "plan_reset_field_",
    "plan_reset_field_spCycle": "plan_reset_field_",
    "plan_reset_field_weekOverrides": "plan_reset_field_",
}

# A deliberate ceiling: adding a runtime key means adding a real concatenation
# first, and the list has to stay small enough to audit by hand.
MAX_RUNTIME_KEYS = 23

KEY_LINE = re.compile(r"^ {4}['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\s*:", re.M)
DATA_I18N = re.compile(r"data-i18n(?:-[a-z-]+)?\s*=\s*[\"']([^\"']+)[\"']")
T_LITERAL = re.compile(r"\bt\(\s*(['\"])([A-Za-z_][A-Za-z0-9_]*)\1")
STRING_TOKEN = re.compile(r"(['\"`])([A-Za-z_][A-Za-z0-9_]*)\1")
OBJECT_KEY = re.compile(r"(?<![\w$])([A-Za-z_][A-Za-z0-9_]*)\s*:")
CONCAT_PREFIX = re.compile(r"\bt\(\s*(['\"])([A-Za-z0-9_]+)\1\s*\+")
CONCAT_TEMPLATE = re.compile(r"\bt\(\s*`([A-Za-z0-9_]+)\$\{")


def read_page():
    with open(PAGE, encoding="utf-8") as fh:
        return fh.read()


def split_dictionaries(src):
    """Return (en_block, es_block, rest) with the dictionaries cut out."""
    i18n = src.index("const I18N={")
    en_start = src.index("en:{", i18n)
    es_start = src.index("es:{", en_start)
    end = src.index("\n};", es_start)
    return src[en_start:es_start], src[es_start:end], src[:en_start] + src[end:]


def dictionary_keys(block):
    return set(KEY_LINE.findall(block))


def referenced_keys(rest):
    keys = set(DATA_I18N.findall(rest))
    keys.update(m.group(2) for m in T_LITERAL.finditer(rest))
    # Keys stored in data tables and object maps, then passed to t() through a
    # variable, plus keys used as phase names (t(ph.key)).
    keys.update(m.group(2) for m in STRING_TOKEN.finditer(rest))
    keys.update(m.group(1) for m in OBJECT_KEY.finditer(rest))
    return keys


def concat_prefixes(rest):
    prefixes = {m.group(2) for m in CONCAT_PREFIX.finditer(rest)}
    prefixes.update(m.group(1) for m in CONCAT_TEMPLATE.finditer(rest))
    return prefixes


def main():
    src = read_page()
    en_block, es_block, rest = split_dictionaries(src)
    en_keys = dictionary_keys(en_block)
    es_keys = dictionary_keys(es_block)
    refs = referenced_keys(rest)
    prefixes = concat_prefixes(rest)

    # 1. The two dictionaries describe the same interface.
    assert en_keys, "could not parse the English dictionary"
    assert en_keys == es_keys, (
        "dictionaries differ; en-only=%s es-only=%s"
        % (sorted(en_keys - es_keys), sorted(es_keys - en_keys))
    )

    # 2. Every runtime exception is justified by a real concatenation, and the
    #    list has not grown without review.
    assert len(RUNTIME_KEYS) <= MAX_RUNTIME_KEYS, (
        "RUNTIME_KEYS grew to %d entries (max %d); justify it in the test"
        % (len(RUNTIME_KEYS), MAX_RUNTIME_KEYS)
    )
    for key, prefix in RUNTIME_KEYS.items():
        assert key.startswith(prefix) and key != prefix, (
            "RUNTIME_KEYS[%r] does not start with its prefix %r" % (key, prefix)
        )
        assert prefix in prefixes, (
            "RUNTIME_KEYS[%r] is not justified: no t(%r + ...) in the source"
            % (key, prefix)
        )
        assert key not in refs, (
            "RUNTIME_KEYS[%r] is already referenced literally; drop the exception"
            % key
        )

    # 3. No dictionary key is orphaned.
    orphans = sorted((en_keys - refs) - set(RUNTIME_KEYS))
    assert not orphans, (
        "unused i18n keys (delete from en and es): %s" % ", ".join(orphans)
    )

    print(json.dumps({
        "en_keys": len(en_keys),
        "es_keys": len(es_keys),
        "referenced": len(refs),
        "runtime_keys": len(RUNTIME_KEYS),
        "concat_prefixes": sorted(prefixes),
        "orphans": orphans,
    }, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print("FAIL: %s" % exc, file=sys.stderr)
        sys.exit(1)
