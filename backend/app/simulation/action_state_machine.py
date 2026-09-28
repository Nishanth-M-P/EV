from enum import Enum, auto
from typing import Dict, Any

class Action(Enum):
    IDLE = 0
    CHARGE = 1
    DISCHARGE = 2
    FAULT = 3

class ActionStateMachine:
    """Simple per‑EV finite‑state machine for action persistence.

    The machine stores the last known action for each EV and provides a
    ``transition`` method that can be consulted by the simulation loop.
    ``overrides`` is a list of safety constraint strings returned by the
    ``ConstraintEngine`` – if any are present the action is forced to IDLE.
    Manual overrides bypass safety overrides because they have already been
    validated upstream.
    """

    def __init__(self) -> None:
        self._state: Dict[str, Action] = {}

    def get_current(self, ev_id: str) -> Action:
        return self._state.get(ev_id, Action.IDLE)

    def transition(
        self,
        ev_id: str,
        requested_action: int,
        overrides: list,
        manual: bool = False,
    ) -> Action:
        """Compute the next action.

        * ``requested_action`` – integer coming from the RL agent after safety
          validation (0 = IDLE, 1 = CHARGE, 2 = DISCHARGE).
        * ``overrides`` – safety constraint messages. Any non‑empty list forces
          the action to IDLE.
        * ``manual`` – True when the decision originates from an operator
          override (already safety‑checked).
        """
        if manual:
            # Operator override is authoritative (already validated).
            next_action = Action(requested_action)
        else:
            # Safety overrides dominate.
            if overrides:
                next_action = Action.IDLE
            else:
                next_action = Action(requested_action)
        self._state[ev_id] = next_action
        return next_action
