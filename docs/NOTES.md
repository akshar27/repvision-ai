Design decisions worth knowing:
- One generic flexion/extension state machine for all three exercises; analyzers differ only in features and per-rep rules.
- A reversal before reaching rest closes the cycle as "did not return" and starts the next cycle at the turning point
  (so a half-extended rep followed by another dip yields two partial reps, never one merged rep).
- "Video began mid-movement" is decided by lead time (movement within `start_lead_ms` of the first valid frame), so a
  stationary bent-elbow start is a partial rep, while a clip that starts mid-rep is uncertain.
- Shared rules: Python configs -> JSON -> TS engine; parity enforced by replaying synthetic scenarios (scripts/export_shared.py).
