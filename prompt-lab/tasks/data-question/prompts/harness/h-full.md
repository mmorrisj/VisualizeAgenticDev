How many SEV1 or SEV2 incidents affected services owned by the payments team in Q3 2026?

- Ownership comes from services.team, not from the service name.
- Count an incident in the quarter it was opened (opened_at), not when it was resolved.
- Q3 2026 is 1 July through 30 September inclusive, in UTC.
- Some incidents were filed twice; do not count rows where duplicate_of is set.
- Severity is stored in mixed case, for example SEV2 and sev2.

Reply with the one SQL query that gives the number, in a ```sql code block.
