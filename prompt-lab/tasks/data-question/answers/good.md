This counts SEV1 and SEV2 incidents opened in Q3 2026 on services the payments team owns, excluding duplicates:

```sql
SELECT COUNT(*)
FROM incidents AS i
JOIN services AS s ON s.id = i.service_id
WHERE s.team = 'payments'
  AND UPPER(i.severity) IN ('SEV1', 'SEV2')
  AND i.opened_at >= '2026-07-01'
  AND i.opened_at < '2026-10-01'
  AND i.duplicate_of IS NULL;
```
