# Live browser smoke check

URL: http://127.0.0.1:8771/

Executed after the recorded HTTP rehearsal, with the same runtime and demo
configuration. These are additional UI checks, not new independent evaluation.

- The app loaded and reported the local backend connected.
- Submitted the CBA FY2025 IT-expense false-premise question through the form.
  It returned in 8.3 seconds and displayed `selected report passages`, with the
  original statement that expenses increased, including drivers and offsets.
- Clicked its citation. The visible source panel showed the CBA FY2025 Profit
  Announcement, PDF page 31, the matching full passage, source block identifier,
  and a local original-report link ending in `#page=31`.
- Visually inspected the source panel. It was readable and scrollable in the
  narrow app viewport. No missing source title or blank quote was observed.
- Submitted CBA FY2025 profit. The first numeric request loaded the retrieval
  encoder and took 22.2 seconds. The UI showed both cash and statutory figures,
  correctly labelled, with source buttons pointing to PDF page 18.
- Input controls disabled during requests and re-enabled on completion.
- Left this candidate open for the user. The older server on port 8770 was not
  stopped or modified. No external model API was called.

This smoke check did not exercise every control, device size, or possible query.
