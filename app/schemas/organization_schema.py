from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.patterns import validate_organization_name


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator('name')
    @classmethod
    def name_rules(cls, v: str) -> str:
        return validate_organization_name(v)


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator('name')
    @classmethod
    def name_rules(cls, v: str) -> str:
        return validate_organization_name(v)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
    updated_at: datetime
