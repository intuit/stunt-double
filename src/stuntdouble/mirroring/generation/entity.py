# ABOUTME: Infers domain entities and produces static field values for realistic generated responses.
# ABOUTME: Encodes reusable heuristics for common business objects like customers, products, and orders.
"""
Entity type inference and static field generation.

Provides domain-specific data generation based on entity types
(customer, product, order, payment, etc.) using static templates.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from ..models import ToolDefinition

logger = logging.getLogger(__name__)


class EntityInference:
    """
    Infers entity types from tool definitions and generates appropriate fields.

    This class analyzes tool names and descriptions to determine what kind of
    entity is being operated on, then generates realistic field data.
    """

    @staticmethod
    def infer_entity_type(tool_def: ToolDefinition) -> str:
        """
        Infer entity type from tool definition.

        Analyzes tool name and description to determine the primary
        entity type being operated on. Uses keyword matching with
        priority ordering (specific patterns override generic ones).

        Args:
            tool_def: Tool definition with name and description

        Returns:
            Entity type string: customer, product, order, payment, user,
            transaction, or generic if no pattern matches

        Example:
            >>> tool_def = ToolDefinition(name="get_customer", description="Get customer by ID", ...)
            >>> EntityInference.infer_entity_type(tool_def)
            'customer'
        """
        # Combine name and description for analysis (case-insensitive)
        combined = f"{tool_def.name} {tool_def.description}".lower()

        # Priority-ordered pattern matching (more specific patterns first)
        # Order matters: check specific patterns before generic ones
        patterns = {
            "customer": ["customer", "client", "account_holder"],
            "product": ["product", "item", "catalog", "inventory", "sku"],
            "order": ["order", "purchase", "cart", "checkout"],
            "payment": ["payment", "charge", "refund", "billing"],
            "transaction": ["transaction", "txn", "transfer"],
            "user": ["user", "profile", "authentication", "account"],
        }

        # Find first match (priority ordering via dict iteration in Python 3.7+)
        for entity_type, keywords in patterns.items():
            if any(keyword in combined for keyword in keywords):
                logger.debug(f"Inferred entity type '{entity_type}' for tool '{tool_def.name}'")
                return entity_type

        # No match found, return generic
        logger.debug(f"No entity type match for tool '{tool_def.name}', using 'generic'")
        return "generic"


class StaticFieldGenerator:
    """
    Generates realistic static field data for different entity types.

    Uses deterministic templates with incrementing IDs and timestamps.
    """

    _counter: int = 0

    # No instance state -- all methods are classmethods or staticmethods.

    @classmethod
    def _next_id(cls) -> int:
        """Get next incrementing ID."""
        cls._counter += 1
        return cls._counter

    def generate_fields(self, entity_type: str) -> dict[str, Any]:
        """
        Generate realistic fields for a given entity type using static templates.

        Creates domain-specific field data with appropriate values
        for common entity types (customer, product, order, payment, user, transaction).

        Args:
            entity_type: Entity type (customer, product, order, payment, user, transaction, generic)

        Returns:
            Dictionary of field names to generated values

        Example:
            >>> generator = StaticFieldGenerator()
            >>> fields = generator.generate_fields("customer")
            >>> print(fields)
            {
                "customer_id": "CUST-000001",
                "name": "John Doe",
                "email": "john.doe@example.com",
                ...
            }
        """
        counter = self._next_id()
        now = datetime.now()

        # Entity-specific templates
        templates: dict[str, dict[str, Any]] = {
            "customer": {
                "customer_id": f"CUST-{counter:06d}",
                "name": f"Customer {counter}",
                "email": f"customer{counter}@example.com",
                "phone": f"+1-555-{counter:04d}",
                "address": f"{100 + counter} Main Street, City, ST 12345",
                "created_at": (now - timedelta(days=counter % 365)).isoformat(),
                "active": True,
            },
            "product": {
                "product_id": f"PROD-{counter:06d}",
                "name": f"Product {counter}",
                "description": f"High-quality product item #{counter}",
                "price": round(9.99 + (counter * 5.50), 2),
                "sku": f"SKU-{counter:06d}",
                "category": ["Electronics", "Clothing", "Home", "Sports"][counter % 4],
                "in_stock": counter % 5 != 0,
                "created_at": (now - timedelta(days=counter % 180)).isoformat(),
            },
            "order": {
                "order_id": str(uuid.uuid4()),
                "customer_id": f"CUST-{(counter % 100):06d}",
                "total": round(49.99 + (counter * 12.50), 2),
                "status": ["pending", "confirmed", "shipped", "delivered"][counter % 4],
                "items_count": 1 + (counter % 10),
                "created_at": (now - timedelta(hours=counter % 720)).isoformat(),
                "updated_at": now.isoformat(),
            },
            "payment": {
                "transaction_id": str(uuid.uuid4()),
                "amount": round(25.00 + (counter * 7.25), 2),
                "currency": "USD",
                "status": ["success", "pending", "failed"][counter % 3],
                "method": ["credit_card", "debit_card", "paypal", "bank_transfer"][counter % 4],
                "timestamp": now.isoformat(),
            },
            "user": {
                "user_id": str(uuid.uuid4()),
                "username": f"user{counter}",
                "email": f"user{counter}@example.com",
                "first_name": ["John", "Jane", "Alex", "Sam", "Chris"][counter % 5],
                "last_name": ["Smith", "Johnson", "Williams", "Brown", "Davis"][counter % 5],
                "role": ["user", "admin", "moderator"][counter % 3],
                "created_at": (now - timedelta(days=counter % 365)).isoformat(),
                "last_login": (now - timedelta(hours=counter % 24)).isoformat(),
            },
            "transaction": {
                "txn_id": f"TXN-{counter:010d}",
                "amount": round(100.00 + (counter * 15.00) * (-1 if counter % 2 else 1), 2),
                "type": ["credit", "debit", "transfer", "refund"][counter % 4],
                "status": ["completed", "pending", "failed"][counter % 3],
                "timestamp": now.isoformat(),
                "account_id": f"ACCT-{(counter % 1000):08d}",
            },
        }

        # Get template for entity type or use generic fallback
        found_template = templates.get(entity_type)
        template: dict[str, Any] = (
            found_template
            if found_template is not None
            else {
                "id": str(uuid.uuid4()),
                "name": f"Item {counter}",
                "created_at": now.isoformat(),
            }
        )

        return template.copy()


__all__ = ["EntityInference", "StaticFieldGenerator"]
