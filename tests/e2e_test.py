"""End-to-end browser test of the study page (headless Chrome via Playwright).

Runs the real page from a local HTTP server and fakes DataPipe + Prolific with
request interception, so nothing touches the network.

    python tests/e2e_test.py            # writes test outputs to tests/out/
"""
import functools
import http.server
import json
import re
import shutil
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs"
OUT = Path(__file__).resolve().parent / "out"
CHROME = shutil.which("google-chrome") or shutil.which("chromium")


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def patched_config(experiment_id="REPLACE_ME", seconds=3):
    src = (SITE / "config.js").read_text()
    src = re.sub(r'DATAPIPE_EXPERIMENT_ID: "[^"]*"', f'DATAPIPE_EXPERIMENT_ID: "{experiment_id}"', src)
    src = re.sub(r'PROLIFIC_COMPLETION_CODE: "[^"]*"', 'PROLIFIC_COMPLETION_CODE: "TESTCODE1"', src)
    src = re.sub(r"SECONDS_PER_GRID: \d+", f"SECONDS_PER_GRID: {seconds}", src)
    return src


def do_run(page, base, query, cfg, answers, wrong_first=False, condition_reply=None, data_status=201):
    captured = {}
    page.route("**/config.js", lambda r: r.fulfill(body=cfg, content_type="application/javascript"))

    def on_condition(route):
        captured["condition_req"] = json.loads(route.request.post_data)
        route.fulfill(status=200, json={"message": "Success", "condition": condition_reply})

    def on_data(route):
        captured.setdefault("data_reqs", []).append(json.loads(route.request.post_data))
        route.fulfill(status=data_status, json={"message": "Success"} if data_status < 300 else {"error": "UPLOAD_ERROR"})

    page.route("https://pipe.jspsych.org/api/condition/", on_condition)
    page.route("https://pipe.jspsych.org/api/data/", on_data)
    page.route("https://app.prolific.com/**", lambda r: r.fulfill(body="<h1>prolific complete</h1>", content_type="text/html"))

    page.goto(f"{base}/index.html{query}")
    page.click("#agree")
    page.wait_for_selector("text=Instructions")
    instr_text = page.inner_text("main")
    page.click("#next")

    page.wait_for_selector("text=Quick check")
    right = "lottery" if "prize draw" in instr_text else "fixed"
    check_text = page.inner_text("main")
    assert ("draw" in check_text) == (right == "lottery") and ("$0.25" in check_text) == (right == "fixed"), check_text
    if wrong_first:
        page.check('input[value="none"]')
        page.click("#next")
        page.wait_for_selector("text=That's not right")
    page.check('input[value="correct"]')
    page.click("#next")

    for ans in answers:  # one entry per grid; None = try to submit blank, then let it time out
        page.wait_for_selector("#ans", timeout=10000)
        assert page.is_disabled("#submit")
        if ans is not None:
            page.fill("#ans", str(ans))
        page.press("#ans", "Enter")
        page.wait_for_selector("#ans", state="detached", timeout=10000)

    page.wait_for_selector("text=Almost done")
    page.check('input[name="eff"][value="6"]')
    page.fill("#comment", "test comment")
    page.click("#next")
    return captured, right, instr_text


def main():
    OUT.mkdir(exist_ok=True)
    srv, base = serve()
    answers = [12, 12, None, 3, 15, 8, 20, 9, 11]  # one blank -> timeout
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])

        # 1) Local mode, forced fixed condition, wrong comprehension answer first.
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        _, right, instr = do_run(page, base, "?condition=fixed", patched_config(), answers, wrong_first=True)
        page.wait_for_selector("text=Local test finished")
        page.screenshot(path=str(OUT / "local_done.png"), full_page=True)
        data = page.evaluate("window.__STUDY_DATA__")
        assert data["meta"]["condition"] == "fixed" and right == "fixed"
        assert data["meta"]["comprehension_attempts"] == 2
        assert len(data["trials"]) == 9
        t_out = [t for t in data["trials"] if t["timed_out"]]
        assert len(t_out) == 1 and t_out[0]["answer"] is None and t_out[0]["rt_ms"] == 3000
        results["local"] = data
        page.close()

        # 2) "Production" mode with fake DataPipe: condition 1 -> lottery, save OK, redirect.
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        q = "?PROLIFIC_PID=5f0000000000000000000abc&STUDY_ID=study1&SESSION_ID=sess1"
        cap, right, instr = do_run(page, base, q, patched_config("EXPTEST123"), answers, condition_reply=1)
        page.wait_for_url("https://app.prolific.com/**", timeout=10000)
        assert "cc=TESTCODE1" in page.url, page.url
        assert cap["condition_req"] == {"experimentID": "EXPTEST123"}
        assert right == "lottery" and "prize draw" in instr
        req = cap["data_reqs"][0]
        assert req["experimentID"] == "EXPTEST123"
        assert req["filename"].startswith("5f0000000000000000000abc_") and req["filename"].endswith(".json")
        saved = json.loads(req["data"])
        assert saved["meta"]["condition"] == "lottery" and saved["meta"]["condition_source"] == "datapipe"
        assert saved["meta"]["prolific_pid"] == "5f0000000000000000000abc" and not saved["meta"]["test_run"]
        (OUT / req["filename"]).write_text(req["data"])
        results["prod"] = saved
        page.close()

        # 3) Save failure -> completion code + download shown, no redirect.
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        cap, _, _ = do_run(page, base, q, patched_config("EXPTEST123"), answers, condition_reply=0, data_status=400)
        page.wait_for_selector("text=couldn't reach our data server", timeout=20000)
        assert "TESTCODE1" in page.inner_text("main")
        assert len(cap["data_reqs"]) == 4  # retried
        page.screenshot(path=str(OUT / "save_failed.png"), full_page=True)
        page.close()

        # 4) Phone-width screen is turned away.
        page = browser.new_page(viewport={"width": 390, "height": 800})
        page.goto(f"{base}/index.html")
        assert "Please use a computer" in page.inner_text("main")
        page.close()

        # Screenshots of the key screens for the README/report.
        page = browser.new_page(viewport={"width": 1100, "height": 950})
        page.route("**/config.js", lambda r: r.fulfill(body=patched_config(seconds=25), content_type="application/javascript"))
        for cond in ("fixed", "lottery"):
            page.goto(f"{base}/index.html?condition={cond}")
            if cond == "fixed":
                page.screenshot(path=str(OUT / "screen_consent.png"), full_page=True)
            page.click("#agree")
            page.wait_for_selector("text=Instructions")
            page.screenshot(path=str(OUT / f"screen_instructions_{cond}.png"), full_page=True)
            page.click("#next")
            page.check('input[value="correct"]')
            page.click("#next")
            page.wait_for_selector("#ans")
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT / f"screen_grid_{cond}.png"), full_page=True)
        browser.close()
    srv.shutdown()
    json.dump(results, open(OUT / "e2e_results.json", "w"), indent=2)
    print("ALL E2E CHECKS PASSED")


if __name__ == "__main__":
    main()
