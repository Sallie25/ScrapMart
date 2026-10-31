"""Explicit listing inputs; decimal strings/integers avoid float price rounding."""
from decimal import Decimal, InvalidOperation
import re
import unicodedata
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Condition = Literal['good_condition','used','faulty','damaged','for_parts']
Unit = Literal['pieces','kilograms','tonnes','bundles']
Visibility = Literal['hidden','approximate','public_site']


def exact_decimal(value, places, upper, *, positive=False):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str,int,Decimal)):
        raise ValueError('Use a decimal string or integer')
    raw = str(value)
    if len(raw)>30 or not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,'+str(places)+'})?',raw,re.ASCII):
        raise ValueError('Invalid decimal precision')
    result = Decimal(raw)
    if not result.is_finite() or result < 0 or result >= upper or (positive and result == 0):
        raise ValueError('Invalid decimal value')
    return result


def normalized(value, *, multiline=False):
    if value is None:
        return None
    if not isinstance(value,str):
        raise ValueError('Invalid text')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise ValueError('Invalid text') from None
    if any(unicodedata.category(c).startswith('C') and c not in '\r\n\t' for c in value):
        raise ValueError('Invalid text')
    value=unicodedata.normalize('NFC',value).strip()
    value=value.replace('\r\n','\n').replace('\r','\n') if multiline else ' '.join(value.split())
    if not value:
        raise ValueError('Invalid text')
    return value


class ListingPatch(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    title: str = Field(default=None,min_length=1,max_length=200)
    category_id: uuid.UUID | None = None
    price: Decimal | None = None
    description: str | None = Field(default=None,max_length=5000)
    condition: Condition | None = None
    quantity: Decimal | None = None
    quantity_unit: Unit | None = None
    price_type: Literal['total','per_unit'] = 'total'
    is_negotiable: bool = False
    location_summary: str | None = Field(default=None,max_length=255)
    lga: str | None = Field(default=None,max_length=100)
    area: str | None = Field(default=None,max_length=100)
    latitude: Decimal | None = Field(default=None,ge=-90,le=90,decimal_places=6)
    longitude: Decimal | None = Field(default=None,ge=-180,le=180,decimal_places=6)
    location_visibility: Visibility = 'approximate'
    directions_allowed: bool = False
    public_location_consent: bool = False

    @field_validator('title','location_summary','lga','area',mode='before')
    @classmethod
    def text_valid(cls,value,info):
        if info.field_name=='title' and value is None:
            raise ValueError('Title is required')
        return normalized(value)

    @field_validator('description',mode='before')
    @classmethod
    def description_valid(cls,value): return normalized(value,multiline=True)

    @field_validator('category_id',mode='before')
    @classmethod
    def category_valid(cls,value):
        if value is None or isinstance(value,uuid.UUID): return value
        try:
            result=uuid.UUID(value)
            if str(result)!=value: raise ValueError()
            return result
        except (ValueError,TypeError,AttributeError):
            raise ValueError('Invalid category') from None

    @field_validator('price',mode='before')
    @classmethod
    def price_valid(cls,value): return exact_decimal(value,2,Decimal('1000000000000'))

    @field_validator('quantity',mode='before')
    @classmethod
    def quantity_valid(cls,value): return exact_decimal(value,3,Decimal('100000000000'),positive=True)

    @field_validator('latitude','longitude',mode='before')
    @classmethod
    def coordinates_valid(cls,value):
        if value is None: return None
        if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)) or len(str(value))>30:
            raise ValueError('Invalid coordinate')
        try:
            result=Decimal(str(value))
            if not result.is_finite(): raise ValueError()
            return result
        except (InvalidOperation,ValueError): raise ValueError('Invalid coordinate') from None


class ListingCreate(ListingPatch):
    title: str = Field(min_length=1,max_length=200)


class EmptyRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)


class PublishRequest(EmptyRequest):
    public_location_consent: Literal[True]

    @field_validator('public_location_consent', mode='before')
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError('Explicit consent required')
        return value
