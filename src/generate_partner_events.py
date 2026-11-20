"""Turn KKBox transactions into the webhook events four billing channels would send.

KKBox is one billing system. A streaming service bills through several: its own
card processor (Stripe-like) plus Apple, Roku and Amazon, each with its own payload
shape, timestamp format and money unit. This script fakes that mess on purpose:

  - first-seen March members are RENEW (KKBox v2 is a renewal cohort, see main())
  - each payment_method_id maps to one channel (assumption, see CHANNEL_BY_METHOD)
  - ~2% of events are re-delivered (webhook retries -> duplicates)
  - ~3% arrive 1-5 days late (land in a later daily partition)
  - ~0.5% of paid events are later refunded
  - ~0.3% are malformed (no amount) -> should end in quarantine, not in the ledger
  - monthly partner payout reports with deliberate mismatches for reconciliation

Output: data/landing/<channel>/dt=YYYY-MM-DD/events.jsonl
        data/landing/payout_reports/<channel>_2017-03.csv
Stdlib only; seeded, so reruns give identical files.
"""
import csv, datetime as dt, hashlib, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/transactions_v2.csv"
LANDING = ROOT / "data/landing"
BACKFILL_DAY = dt.date(2017, 2, 28)  # everything before March lands as one initial load
REPORT_MONTH = "2017-03"

# Assumption: KKBox payment methods are anonymised ints. We map the biggest ones to
# channels so the mix looks like a real multi-platform service (~45% direct).
CHANNEL_BY_METHOD = {"41": "direct", "39": "apple", "38": "apple", "32": "roku",
                     "36": "roku", "40": "amazon", "37": "amazon"}
# Partner cut of gross (simplified; real terms vary by year and deal).
COMMISSION = {"direct": 0.03, "apple": 0.30, "roku": 0.20, "amazon": 0.30}
TPE = dt.timezone(dt.timedelta(hours=8))  # KKBox is Taiwan; Roku/Amazon send local time

rng = random.Random(42)


def hid(*parts, n=16):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:n]


def parse_day(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))


def to_payload(ch, kind, ev_id, sub_id, ts, amount, plan_days, expires, auto_renew):
    """One event in the channel's own format. amount is TWD (int) or None if malformed."""
    product = f"plus_{plan_days}d"
    if ch == "apple":  # App Store Server Notifications v2 style: ms epochs, milli-units
        typ = {"NEW": ("SUBSCRIBED", "INITIAL_BUY"), "RENEW": ("DID_RENEW", None),
               "CANCEL": ("DID_CHANGE_RENEWAL_STATUS", "AUTO_RENEW_DISABLED"),
               "REFUND": ("REFUND", None)}[kind]
        return {"notificationType": typ[0], "subtype": typ[1], "notificationUUID": ev_id,
                "signedDate": int(ts.timestamp() * 1000),
                "data": {"originalTransactionId": sub_id, "transactionId": ev_id, "productId": product,
                         "price": None if amount is None else amount * 1000, "currency": "TWD",
                         "expiresDate": int(dt.datetime.combine(expires, dt.time(), dt.timezone.utc).timestamp() * 1000),
                         "autoRenewStatus": int(auto_renew)}}
    if ch == "direct":  # Stripe webhook style: s epochs, minor units, nested object
        typ = {"NEW": "invoice.paid", "RENEW": "invoice.paid",
               "CANCEL": "customer.subscription.updated", "REFUND": "charge.refunded"}[kind]
        return {"id": f"evt_{ev_id}", "type": typ, "created": int(ts.timestamp()),
                "data": {"object": {"customer": f"cus_{sub_id}", "subscription": f"sub_{sub_id}",
                                    "billing_reason": {"NEW": "subscription_create", "RENEW": "subscription_cycle"}.get(kind),
                                    "amount": None if amount is None else amount * 100, "currency": "twd",
                                    "cancel_at_period_end": kind == "CANCEL", "plan": product,
                                    "period_end": int(dt.datetime.combine(expires, dt.time(), dt.timezone.utc).timestamp())}}}
    local = ts.astimezone(TPE)
    if ch == "roku":  # flat, local-time ISO strings, decimal-string money
        return {"eventType": {"NEW": "Purchase", "RENEW": "Renewal", "CANCEL": "Cancellation", "REFUND": "Refund"}[kind],
                "transactionId": ev_id, "customerId": sub_id, "productCode": product,
                "amount": None if amount is None else f"{amount:.2f}", "currency": "TWD",
                "eventDate": local.isoformat(timespec="seconds"), "expirationDate": expires.isoformat()}
    # amazon: RVS-like receipt, local time without offset (a classic trap)
    return {"receiptId": ev_id, "userId": sub_id, "sku": product,
            "eventType": {"NEW": "PURCHASE", "RENEW": "RENEWAL", "CANCEL": "CANCEL", "REFUND": "REFUND"}[kind],
            "priceTWD": amount, "purchaseDate": local.strftime("%Y-%m-%d %H:%M:%S"),
            "renewalDate": expires.isoformat(), "autoRenewing": bool(auto_renew)}


def main(limit=None):
    out = {}  # (channel, landing_day) -> list of json lines
    ledger = []  # what the partner "actually paid" per paid event, for payout reports
    seen_users = set()
    with open(RAW, encoding="utf-8-sig") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: (r["transaction_date"], r["msno"]))
    for i, r in enumerate(rows[:limit]):
        ch = CHANNEL_BY_METHOD.get(r["payment_method_id"], "direct")
        sub_id = hid(r["msno"], n=20)
        day = parse_day(r["transaction_date"])
        ts = dt.datetime.combine(day, dt.time(), dt.timezone.utc) + dt.timedelta(seconds=rng.randrange(86400))
        # transactions_v2 is KKBox's churn cohort: members whose plan expired in March 2017.
        # A member first seen in March is renewing, not signing up. Only pre-March first
        # sightings are treated as new signups.
        first_time = r["msno"] not in seen_users
        kind = ("CANCEL" if r["is_cancel"] == "1" else
                "NEW" if first_time and day <= BACKFILL_DAY else "RENEW")
        seen_users.add(r["msno"])
        amount = int(r["actual_amount_paid"])
        malformed = rng.random() < 0.003
        ev_id = hid(r["msno"], r["transaction_date"], str(i))
        events = [(kind, ev_id, ts, None if malformed else amount)]
        if kind != "CANCEL" and amount > 0 and not malformed and rng.random() < 0.005:
            events.append(("REFUND", hid(ev_id, "refund"), ts + dt.timedelta(days=rng.randint(1, 10)), amount))
        for k, eid, ets, amt in events:
            payload = to_payload(ch, k, eid, sub_id, ets, amt, r["payment_plan_days"],
                                 parse_day(r["membership_expire_date"]), r["is_auto_renew"] == "1")
            land = max(ets.date(), BACKFILL_DAY)
            if rng.random() < 0.03:
                land += dt.timedelta(days=rng.randint(1, 5))  # late arrival
            line = json.dumps(payload)
            out.setdefault((ch, land), []).append(line)
            if rng.random() < 0.02:  # webhook retry, same id, same day or up to 2 days later
                out.setdefault((ch, land + dt.timedelta(days=rng.randint(0, 2))), []).append(line)
            if amt and k != "CANCEL" and ets.date() >= BACKFILL_DAY + dt.timedelta(days=1) and ets.strftime("%Y-%m") == REPORT_MONTH:
                ledger.append((ch, eid, -amt if k == "REFUND" else amt, ets.date()))

    for (ch, day), lines in out.items():
        p = LANDING / ch / f"dt={day}" / "events.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n")

    # Partner payout reports: what each partner says it paid us for March.
    rep_dir = LANDING / "payout_reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    for ch in COMMISSION:
        rows_out = []
        for c, eid, gross, day in ledger:
            if c != ch or rng.random() < 0.002:  # 0.2% silently missing from partner report
                continue
            if rng.random() < 0.002:
                gross += rng.choice([-1, 1]) * rng.randint(1, 30)  # amount drift (FX/rounding/proration)
            fee = round(gross * COMMISSION[ch], 2)
            rows_out.append([eid, day.isoformat(), gross, fee, round(gross - fee, 2)])
        for _ in range(max(1, len(rows_out) // 1000)):  # 0.1% rows we have no record of
            rows_out.append([hid(ch, str(rng.random())), f"{REPORT_MONTH}-15", 149, round(149 * COMMISSION[ch], 2),
                             round(149 * (1 - COMMISSION[ch]), 2)])
        with open(rep_dir / f"{ch}_{REPORT_MONTH}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["partner_txn_id", "txn_date", "gross_twd", "partner_fee_twd", "net_twd"])
            w.writerows(rows_out)

    n = sum(len(v) for v in out.values())
    print(f"wrote {n} events in {len(out)} partitions; {len(ledger)} paid March events in ledger")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
