"""Which calls run on their own, and which wait for you.

The rule is decided by the request, not by asking a model whether an action
looks risky. A GET cannot change anything, so it runs. Anything else waits for
your yes, unless it is one of the few POSTs below that only read (GraphQL
queries, search endpoints), or you answered "always" for that tool before.
"""

from __future__ import annotations

from charter import Tool

from shipmate.home import read_json, write_json

SAFE_METHODS = {"GET", "HEAD"}

# Linear and Shopify are GraphQL, so every call is a POST. Their queries are
# the tools named *_list and *_get, plus these.
GRAPHQL_PACKS = {"linear", "shopify"}
GRAPHQL_READS = {
    "linear": {
        "viewer",
        "organization",
        "attachments_for_url",
        "search_issues",
        "search_projects",
        "search_documents",
    },
    "shopify": {"order_fulfillment_orders", "variant_inventory_level"},
}

# REST endpoints that read but take their query as a POST body.
POST_READS = {
    "gsheets": {
        "values_batch_get_by_data_filter",
        "spreadsheets_get_by_data_filter",
        "spreadsheets_developer_metadata_search",
    },
    "notion": {"search", "data_sources_query"},
    "tavily": {"search", "extract", "map"},
    "firecrawl": {"search", "map", "scrape", "crawl_params_preview"},
}


def is_read(tool: Tool) -> bool:
    if str(tool.method).upper() in SAFE_METHODS:
        return True
    pack = tool.pack or ""
    if pack in GRAPHQL_PACKS:
        return tool.name.endswith(("_list", "_get")) or tool.name in GRAPHQL_READS[pack]
    return tool.name in POST_READS.get(pack, set())


class Policy:
    """The tools you answered "always" for, kept in ~/.shipmate/policy.json."""

    def __init__(self) -> None:
        self.always: set[str] = set(read_json("policy.json", {}).get("always", []))

    def allows(self, name: str) -> bool:
        return name in self.always

    def allow_always(self, name: str) -> None:
        self.always.add(name)
        write_json("policy.json", {"always": sorted(self.always)})
