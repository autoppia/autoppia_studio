from __future__ import annotations

from typing import Protocol, runtime_checkable

from ica.company_harvesters.schemas import CompanyHarvesterInput, CompanyHarvesterOutput


@runtime_checkable
class ICompanyHarvester(Protocol):
    """Benchmark-facing CompanyHarvester contract.

    Miners should submit implementations that can receive company material and
    return discovered tasks plus the solution package needed to build agents.
    """

    id: str
    name: str

    async def harvest_company(self, request: CompanyHarvesterInput) -> CompanyHarvesterOutput:
        ...


class CompanyHarvesterAdapter:
    """Adapter for existing Studio harvesters that expose `harvest(...)`."""

    def __init__(self, wrapped: object) -> None:
        self.wrapped = wrapped
        self.id = str(getattr(wrapped, "id", getattr(wrapped, "name", "company_harvester")))
        self.name = str(getattr(wrapped, "name", self.id))

    async def harvest_company(self, request: CompanyHarvesterInput) -> CompanyHarvesterOutput:
        harvest = getattr(self.wrapped, "harvest", None)
        if not callable(harvest):
            raise TypeError("Wrapped harvester must expose async harvest(request).")
        return await harvest(request)

