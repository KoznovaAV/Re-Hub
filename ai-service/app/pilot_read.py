"""Read-only reference for synthetic H-03 cases. The caller supplies trusted scope."""

PERIODS = {"2026Q2", "2026Q3"}


def query(rows, scope, request):
    if not isinstance(request, dict):
        return {"status": "clarify"}
    action = request.get("action")
    if not isinstance(action, str):
        return {"status": "clarify"}
    if action not in {"get", "list"}:
        return {"status": "refused"} if action in {"write", "update", "delete", "sql"} else {"status": "clarify"}
    period = request.get("period")
    if not isinstance(period, str) or period not in PERIODS:
        return {"status": "clarify"}
    if action == "get":
        if set(request) != {"action", "period", "client"} or not isinstance(request["client"], str):
            return {"status": "clarify"}
        if request["client"] not in scope:
            return {"status": "refused"}
        result = [row for row in rows if row["id"] == request["client"] and row["period"] == period]
        return {"status": "ok", "rows": result} if result else {"status": "no_data"}
    if set(request) != {"action", "period", "minimum"} or type(request["minimum"]) is not int or request["minimum"] < 0:
        return {"status": "clarify"}
    matches = [row for row in rows if row["id"] in scope and row["period"] == period and row["unsent"] >= request["minimum"]]
    return {"status": "ok", "rows": sorted(matches, key=lambda row: row["id"])}
