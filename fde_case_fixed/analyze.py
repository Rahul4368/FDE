#!/usr/bin/env python3
"""
FDE case study (Sparsh Motors) - audit script. Python 3.8+, standard library only.

Usage (put 2-call-records.md in the same folder as this script):
    python analyze.py                          # full audit -> prints report, writes out/audit.csv + out/findings.json
    python analyze.py path/to/records.md       # audit another records file
    python analyze.py --check [records.md]     # tomorrow's pass/fail check after the prompt fix
    python analyze.py --words submission.md    # word-count check for sections a-f
"""
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
IST = timedelta(hours=5, minutes=30)

HEADER_RE = re.compile(r"^###\s+(C-\d+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*min\s*(\d+)\s*sec", re.M)
LOG_RE = re.compile(r"^(\d\d:\d\d:\d\d)\s+(\w+)\s+(\{.*\})\s*$")
TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)

# Management summary figures (3-weekly-summary.md)
SUMMARY = {"booked": 9, "transferred": 5, "callback": 2, "no_action": 4, "total": 20}


def find_records(arg):
    cands = [arg] if arg else []
    cands += [os.path.join(HERE, "2-call-records.md"),
              os.path.join(os.getcwd(), "2-call-records.md"),
              "/mnt/user-data/uploads/2-call-records.md"]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    sys.exit("ERROR: 2-call-records.md not found. Put it next to analyze.py or pass the path.")


def parse_json(text):
    try:
        return json.loads(text)
    except Exception:
        return {"_unparsed": text}


def parse_log(block):
    calls = []
    cur = None
    for raw in block.splitlines():
        line = raw.rstrip()
        m = LOG_RE.match(line.strip())
        if m and not line.strip().startswith("->"):
            cur = {"ts": m.group(1), "tool": m.group(2), "args": parse_json(m.group(3)), "_resp": ""}
            calls.append(cur)
        elif line.strip().startswith("->") and cur is not None:
            cur["_resp"] = line.strip()[2:].strip()
        elif cur is not None and cur["_resp"] and line.strip():
            cur["_resp"] += line.strip()
    for c in calls:
        c["resp"] = parse_json(c.pop("_resp")) if c["_resp"] else {}
    return calls


def parse_records(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    heads = list(HEADER_RE.finditer(text))
    if not heads:
        sys.exit("ERROR: no call records found in " + path)
    records = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.end():end]
        assistant = re.findall(r"^>\s*\*\*Assistant:\*\*\s*(.+)$", body, re.M)
        caller = re.findall(r"^>\s*\*\*Caller:\*\*\s*(.+)$", body, re.M)
        om = re.search(r"Logged outcome:\s*(.+)", body)
        logged = om.group(1).strip() if om else ""
        lm = re.search(r"```\n(.*?)```", body, re.S)
        calls = parse_log(lm.group(1)) if lm else []
        records.append({
            "id": h.group(1), "when": h.group(2), "secs": int(h.group(3)) * 60 + int(h.group(4)),
            "assistant": assistant, "caller": caller, "logged_label": logged, "calls": calls,
        })
    return records


def to_hhmm(text_time):
    m = TIME_RE.search(text_time)
    if not m:
        return None
    hh, mm, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    if ap == "pm" and hh != 12:
        hh += 12
    if ap == "am" and hh == 12:
        hh = 0
    return "%02d:%02d" % (hh, mm)


def told_time(rec):
    """Time in the assistant's confirmation line (last assistant line with a time and a confirm word)."""
    for line in reversed(rec["assistant"]):
        if re.search(r"\b(done|booked|put you down)\b", line, re.I):
            ms = TIME_RE.findall(line)
            if ms:
                hh, mm, ap = ms[-1]
                return to_hhmm("%s:%s %s" % (hh, mm or "00", ap))
    return None


def analyse(rec):
    calls = rec["calls"]
    tools = [c["tool"] for c in calls]
    lookup = next((c["resp"] for c in calls if c["tool"] == "lookup_customer"), {})
    open_jc = lookup.get("open_job_cards", []) or []
    outcome = next((c["args"].get("outcome") for c in calls if c["tool"] == "log_outcome"), None)
    book = [c for c in calls if c["tool"] == "book_appointment"]
    book_ok = [c for c in book if c["resp"].get("status") == "ok"]
    book_err = [c for c in book if "error" in c["resp"]]
    transfers = [c for c in calls if c["tool"] == "transfer_to_advisor"]
    transfer_no_answer = any(c["resp"].get("status") in ("no_answer", "busy") for c in transfers)

    offered = {}
    for c in calls:
        if c["tool"] == "check_availability":
            for s in c["resp"].get("slots", []) or []:
                offered[s["slot_id"]] = s

    fabricated = [b["args"].get("slot_id") for b in book if b["args"].get("slot_id") not in offered]

    time_mismatch, no_start_local, told, confirmed = False, False, None, None
    if book_ok:
        b = book_ok[0]
        slot = offered.get(b["args"].get("slot_id"), {})
        no_start_local = "start_local" not in slot
        confirmed = b["resp"].get("confirmed_local", "")[-9:-4] if b["resp"].get("confirmed_local") else None
        told = told_time(rec)
        if told and confirmed and told != confirmed:
            time_mismatch = True

    errors = [c["resp"]["error"] for c in calls if isinstance(c["resp"], dict) and "error" in c["resp"]
              and c["tool"] != "lookup_customer"]
    return {
        "id": rec["id"], "when": rec["when"], "secs": rec["secs"], "logged_outcome": outcome,
        "open_job_cards": len(open_jc), "tools": ">".join(tools),
        "called_get_vehicle_status": "get_vehicle_status" in tools,
        "check_availability_calls": tools.count("check_availability"),
        "book_called": bool(book), "book_ok": bool(book_ok), "book_error": book_err[0]["resp"]["error"] if book_err else "",
        "fabricated_slot_id": ";".join(x for x in fabricated if x),
        "told_time": told or "", "confirmed_time_ist": confirmed or "", "time_mismatch": time_mismatch,
        "slots_missing_start_local": no_start_local,
        "transfer_no_answer_no_callback": transfer_no_answer and "log_callback" not in tools,
        "quoted_price_rupees": any("rupees" in a.lower() for a in rec["assistant"]),
        "tool_errors": ";".join(errors),
        "booked_logged_without_ok_booking": outcome == "booked" and not book_ok,
    }


def audit(path):
    recs = parse_records(path)
    rows = [analyse(r) for r in recs]
    n = len(rows)
    by_outcome = {}
    for r in rows:
        by_outcome[r["logged_outcome"]] = by_outcome.get(r["logged_outcome"], 0) + 1
    ids = lambda key: [r["id"] for r in rows if (r[key] if isinstance(r[key], bool) else r[key])]
    avg = sum(r["secs"] for r in rows) / float(n)
    f = {
        "calls": n,
        "logged_outcomes": by_outcome,
        "booked_logged": [r["id"] for r in rows if r["logged_outcome"] == "booked"],
        "book_appointment_ok": ids("book_ok"),
        "booked_logged_without_ok_booking": ids("booked_logged_without_ok_booking"),
        "booked_logged_with_book_error": [r["id"] for r in rows if r["logged_outcome"] == "booked" and r["book_error"]],
        "fabricated_slot_id": [(r["id"], r["fabricated_slot_id"]) for r in rows if r["fabricated_slot_id"]],
        "time_mismatch": [(r["id"], r["told_time"], r["confirmed_time_ist"]) for r in rows if r["time_mismatch"]],
        "bookings_ok_and_time_correct": [r["id"] for r in rows if r["book_ok"] and not r["time_mismatch"]],
        "slots_missing_start_local": ids("slots_missing_start_local"),
        "calls_with_open_job_card": ids("open_job_cards"),
        "get_vehicle_status_calls": ids("called_get_vehicle_status"),
        "transfer_no_answer_no_callback": ids("transfer_no_answer_no_callback"),
        "quoted_price_rupees_no_tool_source": ids("quoted_price_rupees"),
        "tool_errors": [(r["id"], r["tool_errors"]) for r in rows if r["tool_errors"]],
        "avg_duration_sec": round(avg, 1),
        "avg_duration_mmss": "%d:%02d" % divmod(int(round(avg)), 60),
        "summary_matches_logged_outcomes": all(by_outcome.get(k, 0) == v for k, v in SUMMARY.items() if k != "total"),
    }
    return rows, f


def write_outputs(rows, f):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "audit.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(OUT_DIR, "findings.json"), "w", encoding="utf-8") as fh:
        json.dump(f, fh, indent=2)


def show(rows, f):
    n = f["calls"]
    line = "-" * 78
    print(line)
    print("SPARSH MOTORS KOTHRUD - AUDIT (%d calls)" % n)
    print(line)
    print("Logged outcomes (matches management summary: %s): %s" % (f["summary_matches_logged_outcomes"], f["logged_outcomes"]))
    print("Avg duration: %s (summary says 2:53)" % f["avg_duration_mmss"])
    print()
    print("BOOKINGS")
    print("  logged 'booked'                 : %d of %d  %s" % (len(f["booked_logged"]), n, f["booked_logged"]))
    print("  book_appointment status ok      : %d of %d  %s" % (len(f["book_appointment_ok"]), n, f["book_appointment_ok"]))
    print("  ...and told the right time      : %d of %d  %s" % (len(f["bookings_ok_and_time_correct"]), n, f["bookings_ok_and_time_correct"]))
    print("  wrong time told (told vs IST)   : %s" % (f["time_mismatch"],))
    print("  slots lacking start_local       : %s" % (f["slots_missing_start_local"],))
    print("  logged booked, no ok booking    : %d of %d  %s" % (len(f["booked_logged_without_ok_booking"]), len(f["booked_logged"]), f["booked_logged_without_ok_booking"]))
    print("  logged booked after tool error  : %s" % (f["booked_logged_with_book_error"],))
    print("  slot_id never returned by tool  : %s" % (f["fabricated_slot_id"],))
    print()
    print("CARS ALREADY IN WORKSHOP")
    print("  calls with open job card        : %d of %d  %s" % (len(f["calls_with_open_job_card"]), n, f["calls_with_open_job_card"]))
    print("  calls using get_vehicle_status  : %d of %d" % (len(f["get_vehicle_status_calls"]), n))
    print()
    print("OTHER")
    print("  transfer no_answer, no callback : %s" % (f["transfer_no_answer_no_callback"],))
    print("  prices quoted (no tool source)  : %s" % (f["quoted_price_rupees_no_tool_source"],))
    print("  tool errors (excl. NOT_FOUND)   : %s" % (f["tool_errors"],))
    print(line)
    print("Wrote: %s and %s" % (os.path.join(OUT_DIR, "audit.csv"), os.path.join(OUT_DIR, "findings.json")))


def check(rows, f):
    """Tomorrow's check after the prompt fix. Prints PASS/FAIL per test; always exits 0 unless --strict."""
    with_jc = [r for r in rows if r["open_job_cards"]]
    used = [r for r in with_jc if r["called_get_vehicle_status"]]
    offered_slots_to_jc = [r["id"] for r in with_jc if r["check_availability_calls"] > 0]
    tests = [
        ("T1 every call with an open job card called get_vehicle_status (target 100%)",
         len(used) == len(with_jc), "%d of %d" % (len(used), len(with_jc))),
        ("T2 no check_availability on a call with an open job card",
         not offered_slots_to_jc, str(offered_slots_to_jc)),
        ("T3 no 'booked' outcome without an ok book_appointment",
         not f["booked_logged_without_ok_booking"], str(f["booked_logged_without_ok_booking"])),
    ]
    print("TOMORROW'S CHECK (%d calls)" % len(rows))
    allpass = True
    for name, ok, detail in tests:
        allpass = allpass and ok
        print("  [%s] %s  -> %s" % ("PASS" if ok else "FAIL", name, detail))
    print("OVERALL: %s" % ("PASS" if allpass else "FAIL"))
    print("Note: T1/T2 are the fix. T3 is a baseline for the separate ticket; it may still fail until engineering ships it.")
    return allpass


def count_words(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    secs, cur = {}, None
    for ln in lines:
        m = re.match(r"^##\s+([a-g])[\.\)]", ln.strip(), re.I)
        if m:
            cur = m.group(1).lower()
            secs[cur] = []
        elif ln.startswith("## "):
            cur = None
        elif cur and cur != "g":
            secs[cur].append(ln)
    limits = {"a": 250, "c": 80}
    total = 0
    print("WORD COUNT (a-f, tokens with a letter or digit)")
    for k in "abcdef":
        body = "\n".join(secs.get(k, []))
        words = [w for w in re.findall(r"\S+", body) if re.search(r"[A-Za-z0-9]", w)]
        total += len(words)
        lim = limits.get(k)
        flag = "" if lim is None else ("  OK (<%d)" % lim if len(words) < lim else "  OVER (limit %d)" % lim)
        extra = ""
        if k == "d":
            nl = len([l for l in secs.get("d", []) if l.strip()])
            extra = "  non-empty lines: %d (want 10)" % nl
        print("  %s: %4d%s%s" % (k, len(words), flag, extra))
    print("  TOTAL: %d of 800  %s" % (total, "OK" if total <= 800 else "OVER"))


def main():
    args = sys.argv[1:]
    if "--words" in args:
        i = args.index("--words")
        target = args[i + 1] if i + 1 < len(args) else os.path.join(HERE, "submission.md")
        if not os.path.isfile(target):
            sys.exit("ERROR: %s not found" % target)
        count_words(target)
        return
    do_check = "--check" in args
    rest = [a for a in args if not a.startswith("--")]
    path = find_records(rest[0] if rest else None)
    rows, f = audit(path)
    write_outputs(rows, f)
    if do_check:
        ok = check(rows, f)
        if "--strict" in args and not ok:
            sys.exit(1)
    else:
        show(rows, f)


if __name__ == "__main__":
    main()
