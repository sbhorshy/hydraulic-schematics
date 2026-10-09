"""Search budgets exercise real climb control flow, including a real routed sheet."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import proto_optimize as O


def panel(length=100, defects=1):
    return dict(b1=defects, b2max=0, b2tot=0, b3=1.0, b4=10,
                b5=50, v2=0, v13=0, length=length)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.regression = patch.dict(O.NO_REGRESSION, {}, clear=True)
        self.regression.start()
        self.addCleanup(self.regression.stop)

    def search(self, costs, **kwargs):
        log, events = [], []
        with patch.object(O, 'bpanel', side_effect=costs) as evaluate, \
             patch.object(O, 'neighbors', return_value=[('move', n) for n in range(20)]), \
             patch.object(O, 'apply_move', side_effect=lambda current, move: {'from': current, 'move': move}):
            result = O.climb({'seed': True}, {}, {}, log, 'test',
                             progress=events.append, **kwargs)
        return result, log, events, evaluate.call_count

    def test_budget_keeps_best_evaluated_candidate(self):
        result, log, events, calls = self.search(
            [panel(100), panel(90), panel(95), panel(80)], max_evals=4)
        self.assertEqual(calls, 4)
        self.assertEqual(result[1]['length'], 80)
        self.assertEqual(log[-1]['stop_reason'], 'max_evals')
        self.assertEqual(log[-1]['steps'], 2)
        self.assertEqual(events[-1], log[-1])

    def test_step_budget_counts_accepted_moves(self):
        result, log, _, calls = self.search([panel(100), panel(110), panel(90)], max_steps=1)
        self.assertEqual(calls, 3)
        self.assertEqual(result[1]['length'], 90)
        self.assertEqual(log[-1]['stop_reason'], 'max_steps')

    def test_zero_step_or_time_returns_seed_without_probing(self):
        for option, reason in (({'max_steps': 0}, 'max_steps'),
                               ({'max_seconds': 0}, 'max_seconds'),
                               ({'max_evals': 1}, 'max_evals')):
            with self.subTest(option=option):
                result, log, _, calls = self.search([panel()], **option)
                self.assertEqual(calls, 1)
                self.assertEqual(result[0], {'seed': True})
                self.assertEqual(log[-1]['stop_reason'], reason)

    def test_elapsed_budget_stops_after_inflight_evaluation_and_keeps_improvement(self):
        elapsed = [0.0]
        def evaluate(layout, intent, catalog):
            elapsed[0] += 2
            return panel(100 - elapsed[0])
        log = []
        with patch.object(O.time, 'monotonic', side_effect=lambda: elapsed[0]), \
             patch.object(O, 'bpanel', side_effect=evaluate) as call, \
             patch.object(O, 'neighbors', return_value=[('move',)]), \
             patch.object(O, 'apply_move', return_value={'improved': True}):
            result = O.climb({'seed': True}, {}, {}, log, 'clock', max_seconds=3,
                             progress=lambda _: None)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(result[0], {'improved': True})
        self.assertEqual(log[-1]['stop_reason'], 'max_seconds')
        self.assertEqual(log[-1]['elapsed_s'], 4)

    def test_satisfied_seed_needs_no_polish(self):
        result, log, _, calls = self.search([panel(defects=0)])
        self.assertEqual(calls, 1)
        self.assertEqual(log[-1]['stop_reason'], 'target_reached')
        self.assertEqual(result[0], {'seed': True})

    def test_explicit_polish_is_bounded(self):
        _, log, _, calls = self.search([panel(100, 0), panel(90, 0), panel(80, 0)], polish_steps=2)
        self.assertEqual(calls, 3)
        self.assertEqual(log[-1]['stop_reason'], 'polish_steps')
        self.assertEqual(log[-1]['polish_steps_used'], 2)

    def test_local_minimum(self):
        _, log, _, calls = self.search([panel()] * 21)
        self.assertEqual(calls, 21)
        self.assertEqual(log[-1]['stop_reason'], 'local_minimum')

    def test_initial_panel_is_reused_and_counts_in_budget(self):
        _, log, _, calls = self.search([], initial_bp=panel(), max_evals=1)
        self.assertEqual(calls, 0)
        self.assertEqual(log[-1]['evals'], 1)

    def test_reject_invalid_limits(self):
        for option in ({'max_evals': 0}, {'max_steps': -1}, {'polish_steps': -1},
                       {'max_seconds': float('inf')}, {'max_seconds': float('nan')},
                       {'max_evals': 1.5}):
            with self.subTest(option=option), self.assertRaises(ValueError):
                self.search([], **option)

    def test_real_sheet_returns_valid_evaluated_layout_under_budget(self):
        library = Path(O.HERE).parent / 'assets/component-library'
        catalog = json.loads((library / 'component-catalog.json').read_text(encoding='utf-8'))
        intent = {'parts': {'U1': 'hydraulic_user', 'U2': 'hydraulic_user'},
                  'paths': [['U1.return_out', 'U2.pressure_in']], 'taps': []}
        layout = {'canvas': {'width': 800, 'height': 600}, 'externs': {}, 'buses': {},
                  'lanes': [180, 320], 'vlanes': [350], 'labels': {}, 'nodes': {
                      'U1': {'x': 180, 'y': 180, 'w': 180, 'h': 80, 'symbol': 'hydraulic-user.svg'},
                      'U2': {'x': 380, 'y': 300, 'w': 180, 'h': 80, 'symbol': 'hydraulic-user.svg'}}}
        original = copy.deepcopy(layout)
        runs = []
        for _ in range(2):
            log = []
            with patch.object(O, 'bpanel', wraps=O.bpanel) as evaluate:
                result = O.climb(copy.deepcopy(layout), intent, catalog, log, 'real',
                                 max_evals=3, polish_steps=10, progress=lambda _: None)
            self.assertLessEqual(evaluate.call_count, 3)
            self.assertEqual(result[1], O.bpanel(result[0], intent, catalog))
            runs.append((result, log[-1]['stop_reason'], log[-1]['evals']))
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(layout, original)


if __name__ == '__main__':
    unittest.main()
