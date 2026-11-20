```sql
SELECT COUNT(*)
FROM incidents i
JOIN services s ON s.id = i.service_id
WHERE s.name LIKE '%payment%'
  AND i.severity IN ('SEV1', 'SEV2')
  AND i.resolved_at BETWEEN '2026-07-01' AND '2026-09-30';
```
