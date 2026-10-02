import pytest

from shipmate.apps import pack_tools
from shipmate.policy import is_read


def tool(pack: str, name: str):
    return next(t for t in pack_tools(pack) if t.name == name)


@pytest.mark.parametrize(
    "pack, name",
    [
        ("gmail", "threads_list"),
        ("gmail", "messages_get"),
        ("gcalendar", "events_list"),
        ("linear", "issues_list"),  # GraphQL: a POST that only reads
        ("linear", "viewer"),
        ("linear", "search_issues"),
        ("notion", "search"),
        ("shopify", "orders_list"),
    ],
)
def test_reads_run_without_asking(pack, name):
    assert is_read(tool(pack, name))


@pytest.mark.parametrize(
    "pack, name",
    [
        ("gmail", "messages_send"),
        ("gmail", "drafts_create"),
        ("gmail", "threads_trash"),
        ("gcalendar", "events_insert"),
        ("slack", "chat_post_message"),
        ("github", "issues_create"),
        ("linear", "issue_create"),
        ("linear", "issue_delete"),
        ("stripe", "refunds_create"),
        ("shopify", "order_cancel"),
    ],
)
def test_anything_that_changes_something_asks(pack, name):
    assert not is_read(tool(pack, name))


def test_every_graphql_read_named_in_the_policy_exists():
    from shipmate.policy import GRAPHQL_READS, POST_READS

    for pack, names in {**GRAPHQL_READS, **POST_READS}.items():
        have = {t.name for t in pack_tools(pack)}
        assert names <= have, f"{pack}: {names - have} no longer exist"
