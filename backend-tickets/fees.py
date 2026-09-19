"""
fees.py
Stripe processing-fee gross-up so card payers (not the organizer) fully cover
Stripe's cut - the organizer nets exactly the ticket price either way.

A flat 3% markup was tried first but under-covers Stripe's real US card rate
(2.9% + $0.30/transaction): on a $70 ticket that left the organizer $0.29
short after Stripe's cut. This exact formula solves for the charge amount C
such that C - (C * STRIPE_PCT_FEE + STRIPE_FIXED_FEE_CENTS) == net_cents,
so there's no shortfall regardless of ticket price. Update
STRIPE_PCT_FEE/STRIPE_FIXED_FEE_CENTS if your actual negotiated Stripe rate
differs from the standard rate.
"""
import math

STRIPE_PCT_FEE = 0.029
STRIPE_FIXED_FEE_CENTS = 30


def card_price_cents(net_cents):
    """The amount to charge via card so that, after Stripe's fee, the
    organizer still nets `net_cents`."""
    return math.ceil((net_cents + STRIPE_FIXED_FEE_CENTS) / (1 - STRIPE_PCT_FEE))
