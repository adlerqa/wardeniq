"""OpenAPI YAML paths with several operations lost every method after the first.

In a real OpenAPI document each operation has a nested body (summary, responses, ...).
The first nested key cleared the pending path, so `post:` after `get:` was never reported.
"""
from extract import extract_api_endpoints


def test_methods_with_nested_bodies_are_all_found():
    raw = ("paths:\n"
           "  /pets:\n"
           "    get:\n"
           "      summary: List pets\n"
           "      responses:\n"
           "        '200':\n"
           "          description: ok\n"
           "    post:\n"
           "      summary: Create a pet\n"
           "  /pets/{id}:\n"
           "    delete:\n"
           "      summary: Remove a pet\n")
    assert extract_api_endpoints(raw) == "DELETE /pets/{id}\nGET /pets\nPOST /pets"


def test_adjacent_methods_still_work():
    raw = "paths:\n  /pets:\n    get:\n    post:\n  /pets/{id}:\n    delete:\n"
    assert extract_api_endpoints(raw) == "DELETE /pets/{id}\nGET /pets\nPOST /pets"


def test_a_sibling_key_still_ends_the_path():
    raw = "paths:\n  /pets:\n    get:\ncomponents:\n    post:\n"
    assert extract_api_endpoints(raw) == "GET /pets"
