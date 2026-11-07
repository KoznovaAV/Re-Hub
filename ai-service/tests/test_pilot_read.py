from copy import deepcopy
import unittest

from app.pilot_read import query


ROWS = [
    {"id":"A", "period":"2026Q2", "unsent":0, "as_of":"2026-10-20", "source":"pilot-v1"},
    {"id":"A", "period":"2026Q3", "unsent":9, "as_of":"2026-10-20", "source":"pilot-v1"},
    {"id":"B", "period":"2026Q3", "unsent":8, "as_of":"2026-10-20", "source":"pilot-v1"},
    {"id":"C", "period":"2026Q2", "unsent":2, "as_of":"2026-10-20", "source":"pilot-v1"},
    {"id":"C", "period":"2026Q3", "unsent":3, "as_of":"2026-10-20", "source":"pilot-v1"},
    {"id":"OUT", "period":"2026Q3", "unsent":99, "as_of":"2026-10-20", "source":"pilot-v1"},
]
SCOPE = {"A", "B", "C"}
Q2, Q3 = "2026Q2", "2026Q3"


def get(key, period):
    return {"action":"get", "client":key, "period":period}


def search(period, threshold):
    return {"action":"list", "period":period, "minimum":threshold}


# Expected results are explicit indices in the fixed fixture.
CASES = [
    (get("A", Q2), "ok", [0]), (get("A", Q3), "ok", [1]),
    (get("B", Q2), "no_data", []), (get("B", Q3), "ok", [2]),
    (get("C", Q2), "ok", [3]), (get("C", Q3), "ok", [4]),
    (search(Q2, 0), "ok", [0, 3]), (search(Q2, 1), "ok", [3]),
    (search(Q2, 2), "ok", [3]), (search(Q2, 3), "ok", []),
    (search(Q3, 0), "ok", [1, 2, 4]), (search(Q3, 3), "ok", [1, 2, 4]),
    (search(Q3, 4), "ok", [1, 2]), (search(Q3, 8), "ok", [1, 2]),
    (search(Q3, 9), "ok", [1]), (search(Q3, 10), "ok", []),
    (search(Q3, 99), "ok", []), (get("OUT", Q3), "refused", []),
    ({"action":"write"}, "refused", []), ({"action":"sql"}, "refused", []),
    ({"action":"list", "minimum":8}, "clarify", []),
    ({"action":"get", "period":Q3}, "clarify", []),
    (search(Q3, True), "clarify", []),
]


def case_test(request, expected_status, indices):
    def check(self):
        original = deepcopy(ROWS)
        expected = {"status": expected_status}
        if expected_status == "ok":
            expected["rows"] = [original[index] for index in indices]
        self.assertEqual(query(ROWS, SCOPE, request), expected)
        self.assertEqual(ROWS, original)
    return check


class PilotReadTest(unittest.TestCase):
    pass


for index, (request, status, indices) in enumerate(CASES, 1):
    setattr(PilotReadTest, f"test_case_{index:02}", case_test(request, status, indices))
