"""Reusable API schemas and domain conversion helpers."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from slaifi.application.contracts import ReasoningResult
from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import OHLCVBar


class AssetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, max_length=32)
    asset_class: AssetClass = AssetClass.UNKNOWN
    exchange: str | None = Field(default=None, max_length=32)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    instrument_id: str | None = Field(default=None, max_length=128)

    def to_domain(self) -> AssetId:
        return AssetId(
            symbol=self.symbol,
            asset_class=self.asset_class,
            exchange=self.exchange,
            currency=CurrencyCode(self.currency) if self.currency is not None else None,
            instrument_id=self.instrument_id,
        )


class OHLCVBarInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_at: datetime
    end_at: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)

    def to_domain(self, asset: AssetId) -> OHLCVBar:
        return OHLCVBar(
            asset=asset,
            start_at=self.start_at,
            end_at=self.end_at,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


class ReasoningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    interpretation: str | None
    raw_result: dict[str, Any]
    agent: str | None
    agent_version: str | None
    memory_key: str | None
    warnings: list[str]

    @classmethod
    def from_application(cls, result: ReasoningResult) -> "ReasoningResponse":
        return cls(
            status=result.status.value,
            interpretation=result.interpretation,
            raw_result=dict(result.raw_result),
            agent=result.agent,
            agent_version=result.agent_version,
            memory_key=result.memory_key,
            warnings=list(result.warnings),
        )
