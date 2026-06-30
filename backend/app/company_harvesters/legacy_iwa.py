from __future__ import annotations

from app.company_harvesters.local_heuristic import LocalHeuristicCompanyHarvester


class LegacyIwaTrajectoryCompanyHarvester(LocalHeuristicCompanyHarvester):
    """Bridge for the existing external `autoppia_harvester` service.

    The external service is excellent at task -> web trajectory (`/find_trayectory`).
    It is not yet a full company harvester because it does not discover company
    use cases from arbitrary UI/API/docs. This class documents the boundary and
    keeps the adapter slot explicit for the next integration step.
    """

    name: str = "legacy_iwa_trajectory"
    kind: str = "remote_miner"
