"""
Deterministic predicates for inbox-triage.

These were prose in `.claude/skills/inbox-triage/SKILL.md`, re-derived by
judgement on every run — which is why the same errors kept recurring. The half
of the gate that is mechanical lives here instead, where it can be tested.

Judgement that genuinely needs a model — is this sender a real person, is this
an ask only Joel can answer — stays in the skill.

Every public predicate strips the quoted reply chain itself. `read_email`
returns the history inline, so a scan over the raw body reads sign-offs and
rejection language out of *earlier* messages (including Joel's own) and every
long thread eventually looks closed. Callers cannot opt out of the strip, on
purpose.

Usage:
    from src.triage_rules import normalize_subject, detect_rejection
"""

import html
import re
from dataclasses import dataclass
from typing import Optional

JOEL_ADDRESSES = (
    "joelchristabreu4044@gmail.com",
    "ajoelcrist@gmail.com",
)

# ---------------------------------------------------------------- subjects

_SUBJECT_PREFIX = re.compile(r"^\s*(re|fw|fwd|aw|sv)\s*(\[\d+\])?\s*:\s*", re.I)


def normalize_subject(subject: str) -> str:
    """Grouping key for tier-1 thread detection.

    Strips any chain of Re:/Fwd: prefixes, unescapes entities, collapses
    whitespace and casefolds. "Re: FW: Re: Intro Chat" and "intro  chat" are
    the same thread.
    """
    s = html.unescape(subject or "")
    while True:
        stripped = _SUBJECT_PREFIX.sub("", s, count=1)
        if stripped == s:
            break
        s = stripped
    return re.sub(r"\s+", " ", s).strip().casefold()


def is_from_joel(from_header: str) -> bool:
    """Test #1: a search result written by Joel means he spoke last."""
    header = (from_header or "").casefold()
    return any(addr in header for addr in JOEL_ADDRESSES)


# ------------------------------------------------------------ quoted chain

# Gmail's marker wraps across lines when the address is long:
#     On Thu, Aug 20, 2026 at 2:13 PM Liseets Taveras <
#     recruiting+433606714@applytojob.com> wrote:
_QUOTE_MARKERS = (
    re.compile(r"^On .{0,400}?wrote:\s*$", re.M | re.S),
    re.compile(r"^\s*>", re.M),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.M | re.I),
    re.compile(r"^_{10,}\s*$", re.M),
    re.compile(r"^\s*From:.*\n\s*Sent:", re.M | re.I),
)


def strip_quoted_chain(body: str) -> str:
    """Return only the newest message's own text.

    Cuts at whichever quote marker appears first. A body with no marker comes
    back unchanged.
    """
    if not body:
        return ""
    cut = len(body)
    for marker in _QUOTE_MARKERS:
        found = marker.search(body)
        if found and found.start() < cut:
            cut = found.start()
    return body[:cut].strip()


# --------------------------------------------------------------- sentences

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


# --------------------------------------------------------------- the asks

_ASK_PHRASES = (
    "could you", "can you", "would you", "will you",
    "please send", "please share", "please confirm", "please provide",
    "please let me know", "please complete", "please fill",
    "let me know", "send me", "send over", "share a few", "share your",
    "are you available", "are you interested", "do you have time",
    "what times", "when are you", "your availability",
    "get back to me", "confirm your", "sign the", "complete the",
    # soft asks -- an offer that still puts the next move on Joel
    "if you're interested", "if you are interested", "if that sounds",
    "happy to schedule", "happy to set up", "would you be open",
    "are you open to", "worth taking a look", "let us know",
)


def contains_ask(body: str) -> bool:
    """Test #2: does this message ask Joel for something?

    A question mark or any imperative aimed at him. Deliberately generous:
    missing a real ask costs an opportunity, while a false positive only means
    the message goes to the model for judgement.
    """
    own = strip_quoted_chain(body).casefold()
    if "?" in own:
        return True
    return any(phrase in own for phrase in _ASK_PHRASES)


# ---------------------------------------------------------- sign-off (test 3)

_CLOSING_PHRASES = (
    "thanks", "thank you", "thx", "cheers", "sounds good", "sounds great",
    "perfect", "great", "okay cool", "ok cool", "no worries", "np",
    "will keep you posted", "keep you posted", "keep you updated",
    "i will keep you", "i'll keep you", "talk soon", "speak soon",
    "have a great day", "have a good day", "have a great week",
    "looking forward to it", "looking forward to speaking",
    "best regards", "kind regards", "regards", "best", "sincerely",
    "job spec", "see attached", "attached", "fyi",
)

_GREETING = re.compile(
    r"^(hi|hey|hello|dear|good (morning|afternoon|evening))\b", re.I
)


def _is_pleasantry(sentence: str) -> bool:
    s = sentence.strip().strip("-–—:;,.!").casefold()
    if not s:
        return True
    if _GREETING.match(sentence):
        return True
    if len(s.split()) <= 3:          # a bare name, an emoji, "joel"
        return True
    return any(s.startswith(p) or s == p for p in _CLOSING_PHRASES)


def detect_closing_statement(body: str) -> bool:
    """Test #3: is this message nothing but a sign-off?

    Test #2 has strict precedence — an ask anywhere defeats a sign-off,
    because recruiters wrap real requests in friendly packaging:

        "Sounds good! Also, could you send over your updated resume?"

    And the message must be closing material *throughout*. A single trailing
    "Thanks!" does not close a message that also schedules an interview; that
    asymmetry is what keeps this from swallowing a deadline.
    """
    if contains_ask(body):
        return False
    own = strip_quoted_chain(body)
    sentences = _sentences(own)
    if not sentences:
        return False
    if not any(
        any(p in s.casefold() for p in _CLOSING_PHRASES) for s in sentences
    ):
        return False
    return all(_is_pleasantry(s) for s in sentences)


# ------------------------------------------------------------- rejections

_REJECTION_PHRASES = (
    "not moving forward", "not move forward", "moving forward with other",
    "moving forward with another", "other candidates", "another candidate",
    "decided not to proceed", "decided not to move", "will not be proceeding",
    "regret to inform",
    "we have filled", "we've filled", "position has been filled",
    "no longer under consideration", "not be moving ahead",
    "pursue other candidates", "went with another",
    "not selected", "unsuccessful on this occasion",
)


@dataclass(frozen=True)
class Rejection:
    """Where the rejection language is, not what it means.

    `sentence` is evidence for the skill to read: a rejection closes the row it
    *names*, and the same message often pitches a different role. Attributing
    the title is model work — this only says where to look.
    """

    phrase: str
    sentence: str


# "unfortunately" alone means nothing -- recruiters open bad-news-lite with it
# constantly ("unfortunately we were a bit late", "unfortunately the manager is
# out"). It only counts next to an actual rejection cue.
_UNFORTUNATELY = re.compile(
    r"unfortunat\w*[^.!?]{0,140}?"
    r"(not (moving|proceed|select|going)|other candidate|another candidate|"
    r"filled|no longer|decided (not|to pass)|unable to (move|proceed))",
    re.I | re.S,
)


def detect_rejection(body: str) -> Optional[Rejection]:
    """Locate rejection language in the newest message's own text."""
    own = strip_quoted_chain(body)
    for sentence in _sentences(own):
        lowered = sentence.casefold()
        for phrase in _REJECTION_PHRASES:
            if phrase in lowered:
                return Rejection(phrase=phrase, sentence=sentence)
        hit = _UNFORTUNATELY.search(sentence)
        if hit:
            return Rejection(phrase="unfortunately+" + hit.group(1), sentence=sentence)
    return None


# ------------------------------------------------------------------ titles

def unescape_title(value: str) -> str:
    """Undo HTML entity escaping before any tracker lookup or write.

    Most inbound mail is HTML, so an ampersand arrives as `&amp;`. Passing that
    through creates rows titled `Software Verification &amp; QA Specialist`,
    which then match nothing and have to be repaired by hand.
    """
    if not value:
        return ""
    out = html.unescape(value)
    if "&" in out and re.search(r"&[a-zA-Z]+;|&#\d+;", out):
        out = html.unescape(out)          # doubly-escaped: &amp;amp;
    return re.sub(r"\s+", " ", out).strip()
