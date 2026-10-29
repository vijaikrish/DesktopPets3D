"""Calibrate ConureMind's behaviour-group biases against published parrot time budgets.

    C:\\Python315\\python.exe engine\\calibrate.py [iterations=8]

Each iteration simulates one owner day (sim_day.Owner, sunflower + millet given) with a new seed, measures the
daytime (08-22 h) share of each behaviour group and moves the group bias by 0.6 * ln(target / actual) (clipped).
Targets = middle of genome.TIME_BUDGET_TARGET (captive-parrot data: preening ~10 % of daytime, van Zeeland et al.
2023; mostly perching, Rozek & Millam 2011) adapted to a lively desktop companion. 'negative' is only ever pushed
down (bad moods must come from events, not from a quota). The result is written into genome.GROUP_BIAS.
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)                       # pets/<id>/engine (plugin layout)
MANIFEST = os.path.join(os.path.dirname(ENGINE), 'model', 'animations.json')
sys.path.insert(0, HERE)
sys.path.insert(0, ENGINE)
import genome as G          # noqa: E402
import sim_day              # noqa: E402

TARGET = {g: (lo + hi) / 2 for g, (lo, hi) in G.TIME_BUDGET_TARGET.items()}


def measure(seed):
    import importlib
    import conure_mind
    importlib.reload(conure_mind)
    sim_day.ConureMind = conure_mind.ConureMind
    mind, rec, budget, stints, cc, marks = sim_day.run(days=1, seed=seed, verbose=False, skip_last=False)
    tot = sum(v for (part, g), v in budget[0].items() if part == 'day')
    return {g: budget[0].get(('day', g), 0.0) / tot for g in list(TARGET) + ['sleep', 'feeding', 'other']}


def main(iters=8):
    for it in range(iters):
        share = measure(100 + it)
        line = ' '.join(f'{g}={share[g]:.3f}' for g in share)
        print(f'IT {it} {line}')
        for g, tgt in TARGET.items():
            act = max(share[g], 0.003)
            if g == 'negative' and act <= G.TIME_BUDGET_TARGET[g][1]:
                continue
            step = max(-1.0, min(1.0, 0.6 * math.log(tgt / act)))
            G.GROUP_BIAS[g] = round(G.GROUP_BIAS[g] + step, 3)
        print('   GROUP_BIAS', G.GROUP_BIAS)
    share = measure(999)
    print('FINAL', ' '.join(f'{g}={share[g]:.3f}' for g in share))
    path = os.path.join(ENGINE, 'genome.py')
    src = open(path, encoding='utf-8').read()
    new = 'GROUP_BIAS = dict(' + ', '.join(f'{g}={v}' for g, v in G.GROUP_BIAS.items()) + ')'
    src = re.sub(r'GROUP_BIAS = dict\([^)]*\)', new, src, count=1)
    open(path, 'w', encoding='utf-8').write(src)
    print('WROTE', new)


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
