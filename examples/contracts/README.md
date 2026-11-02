# Contracts and receipts

A gold file says which calls an agent must make. A contract (version 2) also says which calls are optional, which are forbidden, and where more than one path is fine. A receipt records exactly what was evaluated, so the same trace can be re-scored later without running anything. All outputs are real (Toolscore 1.11.0, 2026-11-02); run the commands from this directory.

| File | What it is |
| --- | --- |
| `trace.json` | An agent searched flights, checked the weather, and reserved a seat (instead of `book_flight`). |
| `gold.json` | The old expectation: `search_flights`, then `book_flight`. |
| `contract.json` | `search_flights` with a date matcher, then **either** `book_flight` **or** `reserve_seat`; `get_weather` optional; `cancel_booking` forbidden. |

```bash
toolscore eval gold.json trace.json -o gold.out.json --receipt run.receipt.json   # F (38.3%)
toolscore eval contract.json trace.json -o contract.out.json                       # A (95.7%)
toolscore regrade run.receipt.json --gold contract.json                            # 38.3% F -> 95.7% A
```

- [`eval-gold-output.txt`](eval-gold-output.txt): against the gold file the weather check is "unexpected" and `reserve_seat` is "extra": grade F.
- [`eval-contract-output.txt`](eval-contract-output.txt): the contract picks the `reserve_seat` alternative (the higher score; ties go to the first declared), leaves the optional `get_weather` out of the score, and still reports the extra `seat` argument. `contract_metrics` in `contract.out.json` lists every combination's score.
- [`regrade-output.txt`](regrade-output.txt): the receipt held the trace's SHA-256, so `regrade` first checked that the trace is unchanged, then re-scored it with the contract. Nothing was re-run.
