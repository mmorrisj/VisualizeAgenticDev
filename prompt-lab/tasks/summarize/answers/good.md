**Impact:** On 14 October, about 4,300 card authorizations failed (roughly 12% of card payment attempts) for 1 hour 48 minutes, 09:14 to 11:02 UTC. Automatic retries recovered about 3,900 payments; about 400 still need manual follow-up, which Customer Support is handling by 21 October.

**Cause:** configuration change CHG-7781 cut the card-auth database connection pool from 200 to 20, and the morning peak exhausted it.

**Fix:** the change was rolled back at 10:41; failures stopped by 11:02.

**Why detection was slow:** customer support tickets caught it, not monitoring. The error-rate alert's 30-minute window and 15% threshold never triggered, and there was no alert on pool saturation.

**Open actions:**
- Pool saturation alert for payments services (Daniel Okafor, 31 Oct).
- Capacity check for configuration changes that reduce pools or limits (Priya Raman, 7 Nov).
- Shorter alert window (Payments SRE, 31 Oct).

Postmortem review: 20 October.
