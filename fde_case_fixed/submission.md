# FDE case study: Sparsh Motors, Kothrud, 18 to 23 Aug

## a. What actually happened this week

The management summary reports 9 of 20 calls booked. The tool logs support far less.

- 4 of 20 calls have book_appointment status ok (C-01, C-08, C-09, C-18).
- 2 of those 4 told the caller the wrong time. C-08: told 10:00, confirmed 15:30 IST. C-09: told 9:30, confirmed 15:00 IST. Both check_availability results had no start_local.
- 5 of the 9 logged "booked" have no appointment. C-02, C-03, C-05, C-10 never called book_appointment. C-13 got WORKSHOP_CLOSED and logged booked.

So 2 of 20 calls are clean bookings, not 9.

8 of 20 callers had an open job card at lookup (C-02, 04, 07, 11, 14, 16, 17, 20), and every one asked about a car or claim already in the workshop. get_vehicle_status was called in 0 of 20 calls. Six of those 8 were offered a booking slot instead (C-02, 07, 11, 14, 16, 20).

3 of 20 calls quoted rupee prices no tool returned (C-03, C-05, C-08). C-10 promised pickup and drop with no source.

C-15 hit UNKNOWN_SERVICE_TYPE: bodyshop is not configured at KTD-04. C-15 and C-17 ended no_action with no callback.

The summary's "100% answer rate" counts only calls that reached the assistant. I have no source for callers who hung up before that.

## b. One call traced: C-13

- 10:10:18 lookup_customer: C7228, no open jobs. Fine.
- 10:10:52 check_availability for 24 Aug (Sunday): slots empty, site_closed. Correct.
- 10:11:30 check_availability for 23 Aug: returns S-4462 and S-4468. Caller says "Saturday is difficult. Let me think."
- 10:12:20 book_appointment, slot_id S-SUN-0900. **This is where it went wrong.** The caller agreed nothing, and that slot_id was never returned by any tool. It was invented from the Sunday request.
- Result: WORKSHOP_CLOSED. The reference says treat an error as a failed step.
- 10:12:29 log_outcome booked, notes "Saturday 9 am periodic". Compounds the error. Nobody was booked.

## c. Note to the workshop manager

Your weekly report overstates bookings. Of 20 calls, the logs show 4 real bookings, and 2 of those gave the customer the wrong time: C-08 and C-09. Please call those two customers today. Eight callers were asking about cars already in your workshop, and the assistant could not answer them. We are fixing that. I cannot promise a date yet.

## d. Ticket for engineering

1. Title: Assistant ignores open_job_cards, mis-logs bookings, misreads UTC slots (site KTD-04)
2. Source: 2-call-records.md, 20 calls, 18 to 23 Aug; call IDs below.
3. Bug 1: 0 of 20 calls used get_vehicle_status; 8 of 20 had open_job_cards (C-02, 04, 07, 11, 14, 16, 17, 20). Check whether the tool is exposed to the assistant.
4. Bug 2: log_outcome booked allowed without book_appointment ok in 5 of 9 (C-02, 03, 05, 10, 13). Enforce server side.
5. Bug 3: book_appointment called with slot_id never returned by check_availability: C-13, S-SUN-0900. Reject unknown slot_ids.
6. Bug 4: check_availability omits start_local for diagnostic and inspection (C-08, C-09). Assistant read UTC as local. Add start_local.
7. Bug 5: bodyshop not configured at KTD-04 (C-15). Confirm if intended; brief says Sparsh does insurance jobs.
8. Bug 6: transfer_to_advisor no_answer with no log_callback (C-02).
9. Bug 7: no source for prices or pickup and drop in tools (C-03, 05, 08, 10). Block or supply a price tool.
10. Repro and check: python analyze.py --check on any day's export.

## e. Fix I would make tonight

Prompt change, no deploy needed. Add: "If lookup_customer returns open_job_cards, and the caller asks about their car or claim, call get_vehicle_status with that job card first. Do not call check_availability or offer a slot on that call. If the tool errors, call transfer_to_advisor, then log_callback if no_answer."

Check tomorrow: export the day's calls, run python analyze.py --check. T1 passes if every call with open_job_cards called get_vehicle_status (baseline 0 of 8). T2 passes if none of those called check_availability (baseline: 6 of 8 did call it). If T1 stays at 0, the tool is not exposed, and that goes to engineering via ticket line 3.

## f. Two places I did not take the AI's answer

1. Reconciliation. A first pass says the summary matches the logs, since 9, 5, 2, 4 all reconcile. They do, but the logs only record what the assistant claimed. I checked each "booked" against book_appointment and got 4, not 9.
2. Timezone. A natural answer is "a UTC bug, everything is off by 5:30". C-09 says "Friday at 4 pm" for S-4444 (10:30Z), which is correct. The conversion is inconsistent, so I put the fix on start_local being absent, not on a fixed offset.

## g. Session log

Attached separately: export of this chat.
