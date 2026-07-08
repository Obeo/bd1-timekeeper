from __future__ import annotations

from bd1.models import ObservationType, RuntimeState


class StateMachine:
    def __init__(self) -> None:
        self.state = RuntimeState.OFFLINE

    def record(self, observation_type: ObservationType) -> RuntimeState:
        if observation_type == ObservationType.BOOT:
            self.state = RuntimeState.PC_ON
        elif observation_type in {
            ObservationType.FIRST_ACTIVITY,
            ObservationType.ACTIVITY_RESUMED,
            ObservationType.USER_WORKING,
        }:
            self.state = RuntimeState.ACTIVE
        elif observation_type in {ObservationType.IDLE_STARTED, ObservationType.USER_BREAK}:
            self.state = RuntimeState.IDLE
        elif observation_type == ObservationType.SHUTDOWN:
            self.state = RuntimeState.OFFLINE
        return self.state
