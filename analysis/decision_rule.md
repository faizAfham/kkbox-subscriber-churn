# Decision rule (written 2026-11-20, before any result was computed)

**Decision.** Should a monthly subscriber be priced at TWD 149 rather than 99?

**Who.** Users in KKBox `train_v2` (membership expiring in March 2017, with the official churn label) whose
subscription up for renewal is:
- a 30-day plan;
- auto-renew;
- not free (list price > 0);
- paid by payment method 41, the only method that carries every price tier, so that price is not mixed up with
  how people pay.

The tier is the list price of the **subscription that expires in March**. That means the user's last
transaction dated on or before 2017-02-28, not their March transaction. A March transaction is often the
renewal itself, so pricing users by it would leak the outcome: anyone with a March renewal is, by construction,
not a churner.

**Primary metric.** 12-month expected revenue per starting subscriber, `R = p × (1 − (1 − c)^12) / c`. Here
`p` is the list price and `c` is that tier's churn rate (`is_churn`, i.e. no renewal within 30 days of expiry).
It assumes a constant monthly churn rate, and the memo says so.

**Guardrails** (reported; must not look alarming):
- cancel rate (`is_cancel` on a March transaction);
- share of users whose March renewal is at a lower price than the expiring one (downgrade).

**Rule.**
1. **149 pays.** 149's R is above 99's R, the bootstrap 95% interval of the gap is above 0, **and** 149's
   churn is at least 1 point below its break-even churn. → Propose a price test that moves new subscribers
   to 149.
2. **Too close to call.** The interval includes 0, or the margin to break-even is under 1 point. → Run the
   price test before deciding.
3. **Don't raise.** 149's R is below 99's. → Don't raise the price; find out why 149 users leave.

**Confounder check.** Repeat the comparison within tenure bands (under 1 year / 1–2 years / over 2 years) and
pool the bands with Mantel-Haenszel. If the churn gap shrinks by more than half, the memo says tenure, not
price, explains most of it.

**What would change my mind.** Users whose price rose between their previous and their expiring subscription
churn more than the break-even rate allows.
