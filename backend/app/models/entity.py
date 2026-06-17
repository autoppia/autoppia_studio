from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EntityFieldRole = Literal["identifier", "display", "reference", "status", "date", "amount", "metadata"]
EntityRelationshipKind = Literal["belongsTo", "hasOne", "hasMany", "manyToMany", "references"]
EntitySource = Literal["manual", "openapi", "llm_mapper", "imported"]


class EntityField(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    role: EntityFieldRole | str = ""
    required: bool = False
    ref: str = ""
    target: str = ""
    sourcePath: str = ""
    examples: list[Any] = Field(default_factory=list)


class EntityRelationship(BaseModel):
    name: str
    kind: EntityRelationshipKind | str = "references"
    target: str
    via: str = ""
    description: str = ""


class EntityModel(BaseModel):
    entityId: str = ""
    companyId: str = ""
    email: str = ""
    name: str
    description: str = ""
    fields: list[EntityField] = Field(default_factory=list)
    relationships: list[EntityRelationship] = Field(default_factory=list)
    sourceConnectorId: str = ""
    source: EntitySource | str = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: Any = None
    updatedAt: Any = None
