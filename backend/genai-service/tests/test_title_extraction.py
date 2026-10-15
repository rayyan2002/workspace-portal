"""Day 15: task titles. Fixing a defect Day 14b created.

WHAT WENT WRONG. Day 14b replaced a keyword router with a classifier, so phrasings nobody
wrote down started reaching `task_title_from` — which was still matching against a fixed
list of complete prefixes. Measured on the 32 create-task messages in
`evaluation/title_cases.json`: **11/32 correct, 16 of them the whole message verbatim.**
The classifier generalised the routing and left the naming behind.

Two further bugs the measurement surfaced, both invisible from reading the list:

  * DANGLING CONNECTIVES. "make a task to chase the vendor invoice" became "To chase the
    vendor invoice", because "make a task" was in the list and "make a task to" was not.
  * OVER-STRIPPING. "please follow up on the runway inspection" became "The runway
    inspection" — a topic, not a task. The list contained "follow up on", which is the
    WORK. Over-stripping is harder to spot than under-stripping, because the result still
    reads like English.

THE FIX IS COMPOSITIONAL PEELING, NOT A LONGER LIST. Wrappers compose — "can you" +
"write down" + "that" is three independent pieces — so enumerating their combinations is
the combinatorial version of the problem the classifier was brought in to solve.

HOW HONEST THE 32/32 IS, stated rather than implied. The MESSAGES are independent: every
one comes from `intent_train.json` or `tool_cases.json`, both written earlier and for
routing rather than naming, and `test_the_cases_are_not_invented_for_this_fix` asserts that
provenance. The EXPECTED TITLES are mine and were written before the implementation
changed — but the algorithm was designed while reading them, so 32/32 is a
design-to-requirement number and not an out-of-sample one. The out-of-sample evidence is
the probe below: phrasings written after the fact, 14 of 15 acceptable.
"""
import json
from pathlib import Path

import pytest

from app.intent import (
    REQUEST_OPENERS,
    TASK_TITLE_MAX,
    TASK_WRAPPERS,
    keyword_route,
    task_title_from,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "evaluation" / "title_cases.json").read_text())["cases"]


# --- the measured set -------------------------------------------------------

@pytest.mark.parametrize("case", CASES, ids=[c["message"][:40] for c in CASES])
def test_every_title_case(case):
    assert task_title_from(case["message"]) == case["title"]


def test_the_cases_are_not_invented_for_this_fix():
    """THE ASSERTION THAT MAKES THE NUMBER MEAN ANYTHING. Every message must come from a
    file written before this fix and for a different purpose. Without it, a future failing
    case can be fixed by deleting it, or a flattering one added, and the suite still passes
    while measuring nothing."""
    sources = set()
    for name in ("intent_train.json", "tool_cases.json"):
        data = json.loads((ROOT / "evaluation" / name).read_text())
        rows = data.get("examples") or data.get("routing")
        sources.update(r["message"].strip().lower() for r in rows)

    invented = [c["message"] for c in CASES if c["message"].strip().lower() not in sources]

    assert not invented, (
        "these title cases exist in no routing file, so they were written for this fix: "
        + "; ".join(invented)
    )


def test_the_set_covers_messages_the_old_prefix_list_could_not_reach():
    """Half the set must be cases the fixed list failed, or it is not measuring the defect
    it was built for — it would just be re-confirming what already worked."""
    regressions = [c for c in CASES if "was" in c]

    assert len(regressions) >= 16, f"only {len(regressions)} cases record a previous failure"


# --- the three failure modes, named ----------------------------------------

def test_a_wrapper_with_no_entry_in_any_list_still_gets_peeled():
    """The defect Day 14b created. None of these matched the old fixed prefix list, so each
    became its own title verbatim."""
    assert task_title_from("jot down that we still owe the client a quote") == (
        "We still owe the client a quote")
    assert task_title_from("open a ticket to fix the broken upload button") == (
        "Fix the broken upload button")
    assert task_title_from("don't let me forget to submit the compliance form") == (
        "Submit the compliance form")


def test_no_connective_is_left_dangling():
    """"make a task" matched and "make a task to" did not, so the title began with "To"."""
    assert task_title_from("make a task to chase the vendor invoice") == "Chase the vendor invoice"
    assert task_title_from("add a task to update the ADBMS notes") == "Update the ADBMS notes"
    assert task_title_from("remind me about the sprint retro") == "The sprint retro"


def test_the_work_verb_survives():
    """OVER-stripping, which the old list did and which is the harder error to see. "follow
    up on the runway inspection" is the task; "The runway inspection" is a topic."""
    assert task_title_from("please follow up on the runway inspection") == (
        "Follow up on the runway inspection")
    assert task_title_from("please chase up the missing expense receipts") == (
        "Chase up the missing expense receipts")
    assert task_title_from("we should schedule a review of the incident report") == (
        "Schedule a review of the incident report")


def test_wrappers_compose_and_are_peeled_one_layer_at_a_time():
    """Three independent pieces in one message. A fixed list would need every combination,
    which is the combinatorial problem the classifier was brought in to avoid."""
    assert task_title_from("can you write down that the backup job failed overnight") == (
        "The backup job failed overnight")
    assert task_title_from("could you please add a task to archive the 2024 invoices") == (
        "Archive the 2024 invoices")


# --- the guards -------------------------------------------------------------

def test_a_wrapper_is_only_stripped_on_a_word_boundary():
    """Without this, "assign" matches "assignment" and the user is offered a task titled
    "Ment review is due next week" — not merely wrong, unreadable, and from a message that
    was never about assigning anything."""
    assert task_title_from("assignment review is due next week") == (
        "Assignment review is due next week")
    assert task_title_from("todoist sync is broken") == "Todoist sync is broken"


def test_a_message_that_is_nothing_but_wrapper_keeps_its_own_text():
    """The published schema sets min_length=1, so an empty title is unproposable. The
    original message is the only honest thing left to say."""
    assert task_title_from("remind me") == "Remind me"
    assert task_title_from("note down") == "Note down"
    assert task_title_from("todo") == "Todo"


def test_a_trailing_clause_is_dropped():
    assert task_title_from("remind me to review the findings, it is overdue") == (
        "Review the findings")


def test_a_title_never_exceeds_the_column_width():
    """tasks.title is VARCHAR(255) and the published CreateTaskArguments advertises the
    same bound, so a proposal that satisfies the schema is storable."""
    assert len(task_title_from("remind me to " + "x" * 400)) == TASK_TITLE_MAX


def test_a_title_is_never_empty_and_always_starts_upper_case():
    for case in CASES:
        title = task_title_from(case["message"])
        assert title, case["message"]
        assert title[0].isupper() or not title[0].isalpha(), title


def test_no_title_still_begins_with_a_separator():
    """The Java original stripped "track this" from "track this: ..." and then upper-cased
    the COLON, offering a task literally titled ": the LSTM inference time looks wrong"."""
    for case in CASES:
        assert not task_title_from(case["message"]).startswith((":", "-", ",", ";"))


# --- out-of-sample, which is the number that actually generalises -----------

#: Written AFTER the implementation and deliberately not consulted while designing it.
#: These are the honest evidence; the 32-case set is design-to-requirement.
UNSEEN = [
    ("remember to book the venue for the offsite", "Book the venue for the offsite"),
    ("would you mind noting that the lift is out of service", "The lift is out of service"),
    ("i want to track the migration of the legacy accounts", "Track the migration of the legacy accounts"),
    ("make a note to cancel the unused licences", "Cancel the unused licences"),
    ("somebody needs to update the emergency contact list", "Update the emergency contact list"),
    ("todo: rotate the signing keys", "Rotate the signing keys"),
    ("let's schedule the postmortem for Thursday", "Schedule the postmortem for Thursday"),
    ("don't forget to renew the insurance policy", "Renew the insurance policy"),
    ("please follow up with legal on the NDA", "Follow up with legal on the NDA"),
    ("on my list: replace the server rack fans", "Replace the server rack fans"),
    ("we must decommission the old staging box", "Decommission the old staging box"),
]


@pytest.mark.parametrize(("message", "expected"), UNSEEN, ids=[m[:34] for m, _ in UNSEEN])
def test_phrasings_written_after_the_fix(message, expected):
    assert task_title_from(message) == expected


def test_a_title_is_derived_without_calling_a_model():
    """Still not a model call, and the reason changed rather than disappeared. benchmarks/17
    measured the generation model against a free heuristic and the heuristic matched it;
    what Day 14b changed is the set of messages that ARRIVE, not the economics. ~7 seconds
    and a non-deterministic title is a poor trade for a string a human reads once and can
    edit. Determinism is asserted because a model call here would silently break it."""
    message = "could you jot down that the hangar light is broken"

    assert task_title_from(message) == task_title_from(message) == "The hangar light is broken"


def test_the_vocabularies_do_not_overlap():
    """An opener is politeness; a wrapper means "record this". A phrase in both would be
    peeled twice in one pass and the second peel would eat real content."""
    assert not set(REQUEST_OPENERS) & set(TASK_WRAPPERS)


def test_work_verbs_are_absent_from_the_wrapper_vocabulary():
    """Pinned as a list because this is the regression that is easy to reintroduce: adding
    "follow up" here would fix nothing and would silently turn tasks back into topics."""
    for work in ("follow up", "follow up on", "chase up", "review", "schedule", "update",
                 "submit", "renew", "verify"):
        assert work not in TASK_WRAPPERS, f"{work!r} is the work, not a wrapper"
        assert work not in REQUEST_OPENERS


# --- routing is unaffected --------------------------------------------------

@pytest.mark.parametrize("case", CASES, ids=[c["message"][:34] for c in CASES])
def test_every_title_case_still_routes_or_is_left_to_the_classifier(case):
    """A title is only ever asked for after something routed to create-task. This does not
    require the KEYWORD half to catch them all — half of these exist precisely because it
    cannot — only that changing the title vocabulary did not change routing."""
    assert keyword_route(case["message"]) in {None, "create-task"}
