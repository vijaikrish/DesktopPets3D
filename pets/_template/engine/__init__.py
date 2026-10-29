"""Replace with this species' engine. See app/plugin_api.py for the full interface."""


def create_engine(ctx):
    return ExampleEngine(ctx)


class ExampleEngine:
    def __init__(self, ctx):
        self.clip = 'idle'
        self.time = 0.0
        self.mood = 0.0

    def event(self, name, **kw):
        # Handle only events listed in this pet's manifest/menu.
        pass

    def update(self, dt, percepts):
        self.time += dt
        return {'clip': self.clip, 'clip_time': self.time, 'changed': False,
                'emotion': 'neutral', 'emotions': {'neutral': 1.0}, 'fx': [], 'sounds': []}

    def get_state(self):
        return {'version': 1, 'mood': self.mood}

    def set_state(self, state, now=None, hour=None):
        self.mood = float(state.get('mood', 0.0))

    def info(self):
        return {'name': 'ExampleEngine', 'version': 1}
