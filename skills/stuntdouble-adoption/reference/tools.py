"""Real tools of the reference agent.

In a real project these already exist. The adoption skill never edits them; it
reads their signatures so the mocks in ``mocking/mocks.py`` can match exactly.
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def get_customer(customer_id: str) -> dict:
    """Look up a customer by ID."""
    raise NotImplementedError("Replace with the real customer API call")


@tool
def list_bills(customer_id: str, status: str = "all") -> dict:
    """List a customer's bills, optionally filtered by status (all, paid, overdue)."""
    raise NotImplementedError("Replace with the real billing API call")


@tool
def create_invoice(customer_id: str, amount: float, due_date: str | None = None) -> dict:
    """Create an invoice for a customer."""
    raise NotImplementedError("Replace with the real invoicing API call")


TOOLS = [get_customer, list_bills, create_invoice]
