from langchain_core.messages import AIMessage, ToolMessage

from shipmate.chat import tally

API = {"gmail_threads_list", "gmail_messages_send"}
WRITES = {"gmail_messages_send"}


def result(name: str, status: str = "success") -> ToolMessage:
    return ToolMessage("{}", tool_call_id=name, name=name, status=status)


def test_a_claim_with_no_call_behind_it_reads_as_no_changes():
    said_done = [AIMessage("Done, I sent it.")]
    assert tally(said_done, API, WRITES) == "no changes"


def test_counts_what_ran_and_ignores_what_was_refused_or_local():
    turn = [
        result("ToolSearch"),
        result("gmail_threads_list"),
        result("gmail_threads_list"),
        result("gmail_messages_send", status="error"),  # declined at the gate
        result("remember"),
    ]
    assert tally(turn, API, WRITES) == "2 reads · no changes"
    assert tally([*turn, result("gmail_messages_send")], API, WRITES) == (
        "2 reads · changed: gmail_messages_send"
    )
