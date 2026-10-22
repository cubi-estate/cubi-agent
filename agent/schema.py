"""The structured search filter Nemotron extracts from a user's message.

A deliberate subset of the connector's `filter_listings` arguments: the fields a
home-buyer actually states in conversation. `needs_free_text_search` lets the
model say honestly that the request cannot be expressed as a filter (landscape
regions, "near the beach"), which routes to the server-side search fallback.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PropertyType = Literal[
    "apartment", "house", "villa", "townhouse", "penthouse", "studio", "land", "duplex", "farmhouse"
]


class SearchFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: list[str] = Field(description="Towns, cities or neighbourhoods named by the user, in their usual local spelling. Empty if none.")
    type: list[PropertyType] = Field(description="Property types requested. Empty if any type.")
    transaction_type: Literal["sale", "rent"] = Field(description="'rent' for any rental request, else 'sale'.")
    min_price: Optional[float] = Field(description="Minimum price in EUR, or null.")
    max_price: Optional[float] = Field(description="Maximum price in EUR (monthly rent if renting), or null.")
    min_bedrooms: Optional[int] = Field(description="Minimum bedrooms, or null.")
    max_bedrooms: Optional[int] = Field(description="Maximum bedrooms, or null.")
    min_living_area: Optional[float] = Field(description="Minimum living area in m², or null.")
    has_parking: Optional[bool] = Field(description="true only if the user asked for parking or a garage, else null.")
    features: list[str] = Field(description="Structural features asked for, in English Title Case (e.g. 'Balcony', 'Pool', 'Sea View'). Empty if none.")
    lang: Literal["en", "pt", "es", "fr", "de", "nl"] = Field(description="Language the user wrote in.")
    needs_free_text_search: bool = Field(description="false whenever the user names a town or city and the rest fits the fields above (features like balcony or pool DO fit). true only if the request hinges on something no field can hold: a landscape region instead of a town ('Algarve', 'Tuscany'), proximity ('near the beach'), or a mood ('quiet', 'charming').")

    def to_filter_args(self, limit: int = 8) -> dict:
        args: dict = {"lang": self.lang, "limit": limit, "transaction_type": self.transaction_type}
        if self.transaction_type == "rent":
            args["price_period"] = "month"
        for key in ("location", "type", "features"):
            value = getattr(self, key)
            if value:
                args[key] = value
        for key in ("min_price", "max_price", "min_bedrooms", "max_bedrooms", "min_living_area"):
            value = getattr(self, key)
            if value is not None:
                args[key] = value
        if self.has_parking:  # never send false: the connector would exclude homes with parking
            args["has_parking"] = True
        if self.location:
            # "Porto" is also its district and "Valencia" its province: a Porto search
            # listed Felgueiras, 60 km out (live 2026-10-22). The connector pins names
            # that have a city reading to the city; others (Algarve) are unaffected.
            args["city_only"] = True
        return args


def strict_json_schema() -> dict:
    """OpenAI-style strict schema: every property required, no extras."""
    schema = SearchFilter.model_json_schema()
    schema["required"] = list(schema["properties"].keys())
    schema["additionalProperties"] = False
    return schema
