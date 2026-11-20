# Incident report INC-2026-0412: card authorization failures

**Status:** resolved. **Severity:** SEV1. **Report owner:** Priya Raman (Payments SRE).
**Postmortem review:** scheduled for 20 October 2026.

## Summary of events

On 14 October 2026, between 09:14 and 11:02 UTC, a share of card payments failed at authorization. The problem lasted 1 hour 48 minutes. About 4,300 card authorizations failed, roughly 12% of all card payment attempts in that window. Other payment methods, such as bank transfers and stored-balance payments, were not affected.

## Timeline (all times UTC)

- **08:55** A configuration change, CHG-7781, is deployed to the card-auth service. Its purpose was to reduce idle database connections during a planned maintenance window later that week. The change lowered the database connection pool for card-auth from 200 connections to 20.
- **09:14** Traffic rises with the European morning peak. With only 20 connections available, requests to card-auth begin to queue for a database connection. Requests that wait longer than the 3-second authorization timeout fail.
- **09:21** The first customer support tickets arrive reporting declined cards that should have been approved.
- **09:31** The support team, having received 26 tickets in ten minutes, pages the payments on-call engineer. This is the first page of the incident. No automated alert fired: the existing alerts watch error rates over a 30-minute window and were configured with a threshold that the failure rate never crossed.
- **09:38** The on-call engineer, Daniel Okafor, acknowledges the page and begins investigating card-auth. Dashboards show normal CPU and memory, and error rates that are elevated but within alerting thresholds.
- **09:52** A second engineer joins. Initial suspicion falls on the upstream card network, which had a brief issue the previous week. The card network status page shows no problems.
- **10:17** Daniel notices that database connection wait time on card-auth has risen from under 5 milliseconds to more than 2 seconds. He identifies connection pool exhaustion as the cause.
- **10:24** The team links the timing to CHG-7781 and decides to roll the change back rather than raise the pool size by hand.
- **10:41** The rollback of CHG-7781 is deployed. Connection wait times drop below 10 milliseconds within two minutes.
- **11:02** Failure rates return to normal. The incident is declared resolved.

## Customer impact

About 4,300 card authorizations failed over the 1 hour 48 minutes, which is roughly 12% of card payment attempts in that period. The checkout client retried failed authorizations automatically: about 3,900 of the failed payments succeeded on a later retry within 24 hours. About 400 payments did not complete and need manual follow-up by the customer support team, who are contacting the affected merchants. No customer was charged twice; the retry path checks for an existing authorization before charging.

## Root cause

CHG-7781 reduced the card-auth database connection pool from 200 to 20 connections. The change was reviewed as a low-risk configuration update, but the review did not compare the new pool size with peak traffic, which needs about 140 concurrent connections. When the morning peak arrived, requests waited for a free connection and timed out.

## Why detection took 17 minutes

The first sign of the incident came from customer support tickets, not from monitoring. The authorization error-rate alert uses a 30-minute window and a threshold of 15% failed authorizations. The failure rate peaked at 13%, so the alert never fired. There was no alert on connection pool saturation or on database connection wait time.

## What went well

- Customer support recognized the pattern quickly and escalated within ten minutes of the first ticket.
- Automatic retries recovered about 90% of the failed payments without manual work.
- The rollback was quick once the cause was identified.

## What went poorly

- Detection depended on customers noticing.
- The investigation spent 25 minutes on the card network, which was not involved.
- The configuration change was approved without a capacity check.

## Action items

1. Add an alert on database connection pool saturation for card-auth and the other payments services. Owner: Daniel Okafor. Due: 31 October 2026.
2. Add a capacity check to the review checklist for configuration changes that reduce pool sizes, thread counts, or rate limits. Owner: Priya Raman. Due: 7 November 2026.
3. Shorten the authorization error-rate alert window from 30 minutes to 5 minutes and review its threshold. Owner: Payments SRE. Due: 31 October 2026.
4. Complete manual follow-up on the 400 unrecovered payments. Owner: Customer Support lead. Due: 21 October 2026.
