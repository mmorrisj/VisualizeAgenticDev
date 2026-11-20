You are a senior data analyst and an expert in SQLite.

Task: write one SQLite query that returns a single number: how many SEV1 or SEV2 incidents affected services owned by the payments team in Q3 2026.

Requirements:
- Ownership comes from services.team, not from the service name.
- Count an incident in the quarter it was opened (opened_at), not when it was resolved.
- Q3 2026 is 1 July through 30 September inclusive, in UTC. Times are stored as ISO 8601 text such as 2026-09-30T23:40:00Z.
- Some incidents were filed twice; do not count rows where duplicate_of is set.
- Severity is stored in mixed case, for example SEV2 and sev2.

Think step by step:
1. Identify the tables, columns, and joins you need.
2. Check each requirement above against your conditions.
3. Write the query.

Return only the final query, inside a ```sql code block.
