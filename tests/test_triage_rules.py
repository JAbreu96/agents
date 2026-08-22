"""
The mechanical half of the inbox-triage gate.

Every case here is drawn from mail that actually arrived in August 2026, and
most of them are errors this skill already made once: a task telling Joel to
reply to a rejection, a task for a thread he had already answered, a task for a
recruiter who owed *him* the next move.
"""

from src.triage_rules import (
    Rejection,
    contains_ask,
    detect_closing_statement,
    detect_rejection,
    is_from_joel,
    normalize_subject,
    strip_quoted_chain,
    unescape_title,
)

# Verbatim from thread 1a02060e9e3ab049, with the wrapped Gmail quote marker
# that a naive splitter misses.
TRIANGLE_REPLY = """Hi Liseets,

Thank you for the update. I'm looking forward to the call. Here are some
times that work well for me next week:

Wednesday, August 26: 10:00 AM - 12:00 PM or 2:00 PM - 3:30 PM ET

Best,
Joelchrist

On Thu, Aug 20, 2026 at 2:13 PM Liseets Taveras <
recruiting+433606714-075c5aa6@applytojob.com> wrote:

> Hi Joelchrist,
>
> Please respond to this email with a list of dates and times that you would
> be available for an initial phone interview.
>
> Best Regards,
>
> Liseets
"""


# ---------------------------------------------------------------- subjects

def test_prefix_chain_collapses_to_one_key():
    assert normalize_subject("Re: FW: Re: Intro Chat") == "intro chat"
    assert normalize_subject("intro  chat") == "intro chat"


def test_bracketed_and_foreign_prefixes_are_stripped():
    assert normalize_subject("RE[2]: Front End Role") == "front end role"
    assert normalize_subject("AW: Front End Role") == "front end role"


def test_joel_is_recognised_in_both_inboxes():
    assert is_from_joel("Joelchrist Abreu <joelchristabreu4044@gmail.com>")
    assert is_from_joel("<AJOELCRIST@GMAIL.COM>")
    assert not is_from_joel("Marta Tavanez <marta@ubiminds.com>")


# ------------------------------------------------------------ quoted chain

def test_wrapped_gmail_marker_is_cut():
    own = strip_quoted_chain(TRIANGLE_REPLY)
    assert "Thank you for the update" in own
    assert "initial phone interview" not in own
    assert "Liseets Taveras" not in own


def test_outlook_and_angle_quote_styles_are_cut():
    assert strip_quoted_chain("New text.\n\n-----Original Message-----\nold") \
        == "New text."
    assert strip_quoted_chain("New text.\n\n> old quoted line") == "New text."


# ------------------------------------------------------- the key regression

def test_rejection_in_the_quoted_chain_is_not_a_rejection():
    """The failure this design is most likely to introduce.

    A live thread whose history contains a rejection for some *other* role
    must not close the row it is quoting.
    """
    body = """Thanks for clarifying! I'll put you forward for the new opening.

On Mon, Aug 17, 2026 at 9:00 AM Joelchrist Abreu <
joelchristabreu4044@gmail.com> wrote:

> Understood, thanks for letting me know you are not moving forward with
> other candidates for that one.
"""
    assert detect_rejection(body) is None


def test_rejection_reports_the_sentence_not_just_a_boolean():
    body = ("Unfortunately we've moved forward with other candidates for the "
            "Front End role. That said, I have a Full Stack opening on "
            "another team - would you be interested?")
    found = detect_rejection(body)
    assert isinstance(found, Rejection)
    assert "Front End role" in found.sentence
    assert "Full Stack" not in found.sentence


def test_a_re_pitch_still_reads_as_an_ask():
    """Q7: the rejection closes one row; the pitch is scored separately."""
    body = ("Unfortunately we went with another candidate. I have a Full "
            "Stack opening though - would you be interested?")
    assert detect_rejection(body) is not None
    assert contains_ask(body) is True


def test_ordinary_scheduling_mail_is_not_a_rejection():
    assert detect_rejection(TRIANGLE_REPLY) is None


# ------------------------------------------------------ ask beats sign-off

def test_an_ask_anywhere_defeats_a_sign_off():
    body = ("Sounds good! Also, could you send over your updated resume "
            "before Thursday?")
    assert contains_ask(body) is True
    assert detect_closing_statement(body) is False


def test_marta_sign_off_closes_the_thread():
    assert detect_closing_statement(
        "Will keep you posted regarding your application"
    ) is True
    assert detect_closing_statement("Okay cool, I will keep you updated :)") \
        is True


def test_a_trailing_thanks_does_not_close_a_message_that_schedules():
    """A sign-off must not swallow a deadline.

    No question mark, no imperative -- only the requirement that the message
    be pleasantry *throughout* keeps this one alive.
    """
    body = ("We would like to schedule your phone screen for Tuesday at 3pm "
            "ET. Thanks!")
    assert detect_closing_statement(body) is False


def test_muhammad_owes_joel_so_there_is_no_ask():
    """Test #2, not #3, is what suppresses this one."""
    body = "I will be sending the job details to you shortly."
    assert contains_ask(body) is False


def test_a_sign_off_over_quoted_history_still_closes():
    body = "Perfect - thanks!\n\nOn Mon, Aug 17, 2026 at 9:00 AM someone <\na@b.com> wrote:\n\n> could you please share a few times?"
    assert detect_closing_statement(body) is True


# ------------------------------------------------------------------ titles

def test_escaped_ampersand_is_repaired_before_any_write():
    assert unescape_title("Software Verification &amp; QA Specialist") \
        == "Software Verification & QA Specialist"
    assert unescape_title("Systems Integration &amp;amp; Validation") \
        == "Systems Integration & Validation"
    assert unescape_title("R&amp;D  Engineer&#39;s Assistant") \
        == "R&D Engineer's Assistant"
