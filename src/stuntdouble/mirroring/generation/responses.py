"""
Response builders for different operation types.

Generates appropriate response structures for list, get, create,
update, delete, and generic operations.
"""

import logging
import random
import uuid
from datetime import datetime
from typing import Any

from ..models import ToolDefinition
from .entity import StaticFieldGenerator

logger = logging.getLogger(__name__)


class ResponseBuilder:
    """
    Builds responses for different operation types (list, get, create, etc.).
    """

    def __init__(self, field_generator: StaticFieldGenerator):
        """
        Initialize response builder.

        Args:
            field_generator: Field generator for creating entity data
        """
        self.field_generator = field_generator

    def build_list_response(self, entity_type: str) -> dict[str, Any]:
        """
        Generate list/search response with multiple items.

        Args:
            entity_type: Type of entity to list

        Returns:
            List response with items array and pagination metadata
        """
        # Generate 3-5 items with static data
        item_count = random.randint(3, 5)
        items = [self.field_generator.generate_fields(entity_type) for _ in range(item_count)]

        return {
            "items": items,
            "total": random.randint(item_count, 100),
            "page": 1,
            "limit": 10,
            "has_more": random.random() < 0.3,
        }

    def build_entity_response(self, entity_type: str) -> dict[str, Any]:
        """
        Generate single entity response (get/fetch operations).

        Args:
            entity_type: Type of entity to generate

        Returns:
            Single entity object
        """
        return self.field_generator.generate_fields(entity_type)

    def build_creation_response(self, entity_type: str) -> dict[str, Any]:
        """
        Generate creation response with new entity data.

        Args:
            entity_type: Type of entity created

        Returns:
            Created entity with creation flag
        """
        entity = self.field_generator.generate_fields(entity_type)
        entity["created"] = True
        return entity

    def build_update_response(self, entity_type: str) -> dict[str, Any]:
        """
        Generate update response with updated entity data.

        Args:
            entity_type: Type of entity updated

        Returns:
            Updated entity with update metadata
        """
        entity = self.field_generator.generate_fields(entity_type)
        entity["updated"] = True
        entity["updated_at"] = datetime.now().isoformat()
        return entity

    def build_deletion_response(self, entity_type: str) -> dict[str, Any]:
        """
        Generate deletion confirmation response.

        Args:
            entity_type: Type of entity deleted

        Returns:
            Deletion confirmation with ID and timestamp
        """
        return {
            "deleted": True,
            "id": str(uuid.uuid4()),
            "entity_type": entity_type,
            "timestamp": datetime.now().isoformat(),
        }

    def build_generic_response(self, tool_def: ToolDefinition, entity_type: str) -> dict[str, Any]:
        """
        Generate generic success response for unrecognized operations.

        Args:
            tool_def: Tool definition
            entity_type: Inferred entity type

        Returns:
            Generic success response
        """
        response = {
            "status": "success",
            "tool": tool_def.name,
            "data": self.field_generator.generate_fields(entity_type),
        }
        return response

    def build_filtered_list(
        self, entity_type: str, pagination: dict[str, Any], filters: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate list response with pagination and filters applied.

        Args:
            entity_type: Type of entity to generate
            pagination: Pagination parameters (limit, page, offset)
            filters: Filter parameters to apply to items

        Returns:
            List response with filtered items
        """
        limit = pagination.get("limit", 10)
        page = pagination.get("page", 1)

        # Generate items
        items = []
        for _ in range(limit):
            item = self.field_generator.generate_fields(entity_type)
            # Apply filters to generated data
            for filter_key, filter_value in filters.items():
                if filter_key in item or filter_key.lower() in [k.lower() for k in item.keys()]:
                    item[filter_key] = filter_value
            items.append(item)

        return {
            "items": items,
            "total": random.randint(limit, 500),
            "page": page,
            "limit": limit,
            "has_more": random.random() < 0.5,
        }

    def build_entity_with_ids(self, entity_type: str, id_params: dict[str, Any]) -> dict[str, Any]:
        """
        Generate single entity response with IDs from input echoed back.

        Args:
            entity_type: Type of entity to generate
            id_params: ID parameters from input

        Returns:
            Entity with input IDs
        """
        entity = self.field_generator.generate_fields(entity_type)
        # Override with input IDs
        for id_key, id_value in id_params.items():
            entity[id_key] = id_value
        return entity

    def build_creation_with_input(self, entity_type: str, input_params: dict[str, Any]) -> dict[str, Any]:
        """
        Generate creation response incorporating input data.

        Args:
            entity_type: Type of entity to generate
            input_params: All input parameters

        Returns:
            Creation response with input fields merged
        """
        entity = self.field_generator.generate_fields(entity_type)
        # Merge input params (simulating server taking input)
        entity.update(input_params)
        entity["created"] = True
        return entity

    def build_update_with_ids(
        self, entity_type: str, id_params: dict[str, Any], input_params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate update response with IDs and updated fields.

        Args:
            entity_type: Type of entity to generate
            id_params: ID parameters from input
            input_params: All input parameters

        Returns:
            Update response with IDs and updated fields
        """
        entity = self.field_generator.generate_fields(entity_type)
        entity.update(id_params)
        entity.update(input_params)
        entity["updated"] = True
        entity["updated_at"] = datetime.now().isoformat()
        return entity

    def build_deletion_with_ids(self, entity_type: str, id_params: dict[str, Any]) -> dict[str, Any]:
        """
        Generate deletion confirmation with specific ID from input.

        Args:
            entity_type: Type of entity being deleted
            id_params: ID parameters from input

        Returns:
            Deletion confirmation with input ID
        """
        # Use first ID from input if available
        deleted_id = list(id_params.values())[0] if id_params else str(uuid.uuid4())
        return {
            "deleted": True,
            "id": deleted_id,
            "entity_type": entity_type,
            "timestamp": datetime.now().isoformat(),
        }

    def build_generic_with_echo(self, entity_type: str, input_params: dict[str, Any]) -> dict[str, Any]:
        """
        Generate generic response echoing input parameters.

        Args:
            entity_type: Type of entity to generate
            input_params: All input parameters

        Returns:
            Generic response with input echoed back
        """
        return {
            "status": "success",
            "input": input_params,
            "data": self.field_generator.generate_fields(entity_type),
        }


__all__ = ["ResponseBuilder"]
