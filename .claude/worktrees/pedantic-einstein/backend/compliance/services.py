from __future__ import annotations

"""
backend.compliance.services
---------------------------

Thin service boundary for Phase E deterministic CGDCR compliance evaluation.

This layer is responsible only for:
  - building a ComplianceContext from plot + building_contract + GDCR config
  - invoking the ComplianceEngine
  - returning the ComplianceResult DTO

It must not:
  - recompute geometry
  - mutate upstream layout contracts
  - perform any logging or persistence side-effects
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tp_ingestion.models import Plot

from residential_layout.building_aggregation import BuildingLayoutContract

from .engine import ComplianceEngine, ComplianceResult
from .extractor import ComplianceMetricExtractor, ComplianceMetricExtractorInput
from .gdcr_config import GdcrConfig, load_gdcr_config


_DEFAULT_GDCR_PATH = Path("GDCR.yaml")


@dataclass(frozen=True)
class ComplianceServiceConfig:
    gdcr_path: Path = _DEFAULT_GDCR_PATH


class ComplianceService:
    """
    Stateless façade for deterministic CGDCR compliance evaluation.
    """

    def __init__(
        self,
        config: Optional[ComplianceServiceConfig] = None,
        engine: Optional[ComplianceEngine] = None,
        extractor: Optional[ComplianceMetricExtractor] = None,
    ) -> None:
        self._config = config or ComplianceServiceConfig()
        self._engine = engine or ComplianceEngine()
        self._extractor = extractor or ComplianceMetricExtractor()
        self._gdcr: Optional[GdcrConfig] = None

    def _get_gdcr(self) -> GdcrConfig:
        if self._gdcr is None:
            self._gdcr = load_gdcr_config(self._config.gdcr_path)
        return self._gdcr

    def evaluate_gdcr_compliance(
        self,
        plot: Plot,
        building_contract: BuildingLayoutContract,
    ) -> ComplianceResult:
        """
        Deterministic evaluation entrypoint: build ComplianceContext once,
        then evaluate rules using ComplianceEngine.
        """
        gdcr = self._get_gdcr()
        extract_input = ComplianceMetricExtractorInput(
            plot=plot,
            building=building_contract,
            gdcr=gdcr,
        )
        context = self._extractor.build_context(extract_input)
        return self._engine.evaluate(context)

