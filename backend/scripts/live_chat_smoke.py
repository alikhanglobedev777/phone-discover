"""Smoke-test deployed Render APIs using disposable chat sessions.

This script runs on GitHub-hosted CI (network-enabled). It performs 7 bounded
anonymous chat requests with web research explicitly disabled and deletes each
test session in finally to remove the test context and query analytics.
No production catalog edits, score changes, or provider API calls are requested.
"""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

WEB = "https://phone-discover-web.onrender.com"
API = "https://phone-discover-api.onrender.com"
TIMEOUT = 50
TESTED = 0


def call(method, url, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "PhoneDiscoverLiveSmoke/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = response.read(1_000_000)
                if response.status == 204:
                    return {}
                if "application/json" not in response.headers.get("Content-Type", ""):
                    return {"html": body.decode("utf-8", errors="replace")}
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read(450)
            if exc.code in (502, 503, 504) and attempt < 2:
                time.sleep(5)
                continue
            raise AssertionError(
                f"{method} {url.split('?')[0]}: HTTP {exc.code}: "
                + body.decode("utf-8", errors="replace")
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                raise AssertionError(f"{method} {url}: connectivity failure: {exc}") from exc
            time.sleep(5)


def chat(session, message):
    global TESTED
    result = call("POST", API + "/api/recommendations/converse/", {
        "session_id": session, "message": message,
        "research": False, "guidance": False, "use_memory": True,
    })
    TESTED += 1
    assert isinstance(result, dict) and result.get("session_id") == session, (
        message, result.get("detail", "No matching session")
    )
    return result


def check(test, condition):
    assert condition, f"FAIL: {test}"
    print(f"PASS: {test}", flush=True)


def main():
    homepage = call("GET", WEB + "/")
    check("Frontend responds with Phone Discover HTML",
          "Phone Discover" in homepage.get("html", ""))
    health = call("GET", API + "/api/health/")
    check("Django API health check", health.get("status") == "ok")
    status = call("GET", API + "/api/catalog/status/")
    check("Catalog status available", status.get("catalog_status") in (
        "ready", "missing_prices", "empty"))
    sessions = [str(uuid.uuid4()) for _ in range(3)]
    try:
        exact_pixel = chat(sessions[0], "Google Pixel 7a information")
        pixel_slugs = [x["slug"] for x in exact_pixel.get("catalog_details", [])]
        check("Pixel 7a finds the exact published local model",
              pixel_slugs == ["google-pixel-7a"])
        check("Pixel 7a details link points to the correct modal record",
              exact_pixel["catalog_details"][0]["detail_api_url"]
              == "/api/catalog/devices/google-pixel-7a/")

        ultra = chat(sessions[1], "Samsung S26 Ultra")
        check("S26 Ultra is never replaced by S26",
              [x["slug"] for x in ultra.get("catalog_details", [])]
              == ["samsung-galaxy-s26-ultra"])
        compare = chat(sessions[1], "Compare it with Google Pixel 7a")
        pair = compare.get("comparison") or {}
        check("Pronoun comparison uses last phone and new exact phone",
              [x["slug"] for x in pair.get("phones", [])]
              == ["samsung-galaxy-s26-ultra", "google-pixel-7a"])
        check("Comparison only names a leader where both editorial scores exist",
              all(
                  row.get("leader_slug") is None
                  if row.get("first_score") is None or row.get("second_score") is None
                  else row.get("leader_slug") in (
                      None, pair["phones"][0]["slug"], pair["phones"][1]["slug"]
                  )
                  for row in pair.get("dimensions", [])
              ))
        battery = chat(sessions[1], "Which one has better battery?")
        check("Follow-up keeps the same two phones",
              [x["slug"] for x in (battery.get("comparison") or {}).get("phones", [])]
              == ["samsung-galaxy-s26-ultra", "google-pixel-7a"])

        camera = chat(sessions[2], "Best camera phone")
        suggestions = camera.get("specs_results") or []
        priced = camera.get("results") or []
        check("Best-camera chat returns a structured response",
              isinstance(suggestions, list) and isinstance(priced, list)
              and "explanation" in camera)
        check("Unpriced phones never claim verified local prices",
              all(x.get("price_status") == "not_verified_for_filters"
                  and (x.get("editorial_fit") is None
                       or any(v is not None for v in
                              x.get("dimension_scores", {}).values()))
                  for x in suggestions))
        shown = [x["slug"] for x in suggestions] + [
            x["device"]["slug"] for x in priced
        ]
        filtered = chat(sessions[2], "Show only PTA approved options")
        check("PTA follow-up preserves the filter",
              filtered.get("criteria", {}).get("pta_status") == "approved")
        check("PTA follow-up only uses previously shown phones",
              all(x["device"]["slug"] in shown
                  for x in filtered.get("results", []))
              and filtered.get("specs_results") == [])
        print(f"All live checks passed; {TESTED} test chat requests.", flush=True)
    finally:
        for session in sessions:
            try:
                call("DELETE", API + f"/api/recommendations/conversation/{session}/")
                print("Deleted disposable test conversation", flush=True)
            except Exception as exc:
                print("WARNING: test conversation cleanup failed:", str(exc), file=sys.stderr)
                # Cleanup failures are still a test failure, not an ignored side effect.
                raise


if __name__ == "__main__":
    main()
