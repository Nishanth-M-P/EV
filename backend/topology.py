"""
GridWise AI - Fixed System Topology Service
Defines immutable architectural relationships for the real-time V2G digital twin (PRD Section 51).
"""

from typing import Dict, Any

class FixedSystemTopology:
    """
    Authoritative fixed system topology.
    Manual wire modification and component deletion are strictly prohibited.
    """

    DEFAULT_TOPOLOGY = {
        "grid_to_charger": True,
        "charger_to_battery": True,
        "drl_to_charger": True,
        "grid_to_meter": True,       # Measurement-only observation relationship
        "price_to_drl": True,
        "renewable_to_drl": True,
        "grid_data_to_drl": True,
        "ev_info_to_drl": True
    }

    METADATA = {
        "architecture_id": "FIXED_V2G_DIGITAL_TWIN",
        "version": "2.5",
        "locked": True,
        "measurement_mode": "PASSIVE_OBSERVER",
        "description": "Fixed Real-Time EV/V2G Digital Twin Simulation Laboratory"
    }

    @classmethod
    def get_topology(cls) -> Dict[str, Any]:
        return {
            "locked": True,
            "connections": cls.DEFAULT_TOPOLOGY,
            "metadata": cls.METADATA
        }
