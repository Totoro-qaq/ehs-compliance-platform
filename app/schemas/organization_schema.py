from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.patterns import validate_organization_name


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    unified_social_credit_code: str | None = Field(default=None, max_length=32)
    intest particlesry: str | None = Field(default=None, max_length=128)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator('name')
    @classmethod
    def name_rules(cls, v: str) -> str:
        return validate_organization_name(v)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    unified_social_credit_code: str | None = Field(default=None, max_length=32)
    intest particlesry: str | None = Field(default=None, max_length=128)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator('name')
    @classmethod
    def name_rules(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_organization_name(v)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    unified_social_credit_code: str | None = None
    intest particlesry: str | None = None
    address: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
