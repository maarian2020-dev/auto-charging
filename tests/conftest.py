import pytest

from autocharging.config import Config
from autocharging.plug import PlugState


class FakePlug:
    def __init__(self):
        self.on = False
        self.watts = 0.0

    def read(self):
        return PlugState(self.on, self.watts)

    def set_state(self, on):
        self.on = on
        return True


@pytest.fixture
def cfg():
    return Config(device_id="x", ip="127.0.0.1", local_key="k", target="movil", full_samples=3)


@pytest.fixture
def plug():
    return FakePlug()
