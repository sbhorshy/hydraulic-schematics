# -*- coding: utf-8 -*-
"""Differential routing regression against an explicitly supplied old renderer.

Run from any directory; original drawings and scripts are never modified:
  python test_route_pruning.py --baseline-script /path/to/old/render_l0_sheet.py \
      --repo-root /path/to/repo [--report /tmp/route-regression.json]

The baseline must be the unmodified pre-pruning renderer, including any existing
uncommitted fixes. Both renderers use identical input copies and symbol files.
Elapsed times are diagnostic only; no timing threshold determines test success.
"""
import argparse
import contextlib
import copy
import functools
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_l0_sheet as candidate
import proto_optimize as optimizer
import layout_engine as engine


def load_baseline(path):
    spec = importlib.util.spec_from_file_location('unpruned_renderer', str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Catalog/asset contents are held fixed, irrespective of the baseline's
    # historical installation directory.
    module.SKILL_LIB = candidate.SKILL_LIB
    module.SKILL_CATALOG = candidate.SKILL_CATALOG
    return module


def read_case(name, source, intent_name, layout_name, migrate_ports=False,
              assembly_groups=False):
    intent = candidate.load_yaml(str(source / intent_name))
    layout = json.loads((source / layout_name).read_text(encoding='utf-8'))
    if assembly_groups:
        # The CDF drawing uses an extension handled only by its own renderer.
        # This test copy expresses the same membership using supported groups;
        # parts and connections remain exactly the source's serial circuit.
        intent['groups'] = [dict(id=key, label=value['label'],
                                 members=value['members'], reason='assembly')
                            for key, value in intent.pop('assemblies').items()]
    if migrate_ports:
        # Explicit old-name migration in the copied fixture only. No topology
        # or routing preference changes; these sockets were renamed in 2026-09.
        renames = {'QDP-001.inlet': 'QDP-001.aircraft_side',
                   'QDR-001.inlet': 'QDR-001.aircraft_side'}
        intent['paths'] = [[renames.get(token, token) for token in path]
                           for path in intent['paths']]
        catalog = json.loads(Path(candidate.SKILL_CATALOG).read_text())
        # As in the diagnostic benchmark, rebuild this historical layout with
        # current rules/catalog; its FSOV symbol also predates current ports.
        layout, structure = engine.rules(intent, catalog, dict(engine.P), layout)
        layout, _ = engine.guard(layout, structure, dict(engine.P))
    for node in layout['nodes'].values():
        asset = candidate.resolve_asset(node['symbol'], candidate.SKILL_LIB,
                                        str(source))
        if not Path(asset).is_file():
            raise FileNotFoundError(asset)
        # Make both evaluation (which has no workdir) and rendering resolve to
        # the very same existing asset, preserving local overrides and geometry.
        node['symbol'] = str(Path(asset).resolve())
    return name, intent, layout


def cases_from_repo(repo):
    source = repo / '1#系统原理图'
    seeds = [
        read_case('current-23', source, '1#系统.intent.yaml', '1#系统.layout.json'),
        read_case('compatible-22', source / 'skill-chain-e2e',
                  '1#系统.intent.yaml', '1#系统.layout.json', migrate_ports=True),
        read_case('filter-series', source / 'CDF-001装配图',
                  'case_drain_filter.intent.yaml', 'case_drain_filter.layout.json',
                  assembly_groups=True),
    ]
    cases = []
    for name, intent, layout in seeds:
        cases.append((name, intent, layout))
        # Fixed seed, real optimizer moves: includes node displacement, bus
        # displacement and horizontal/vertical corridor changes.
        moves = optimizer.neighbors(layout)
        random.Random(19).shuffle(moves)
        accepted = 0
        for move in moves:
            changed = optimizer.apply_move(layout, move)
            if changed is None:
                continue
            cases.append(('%s-move-%02d' % (name, accepted), intent, changed))
            accepted += 1
            if accepted == 5:
                break
    return cases


def geometry(renderer, intent, layout, catalog):
    sheet = renderer.Sheet(copy.deepcopy(intent), copy.deepcopy(layout), catalog,
                           cat_dir=candidate.SKILL_LIB)
    sheet.place()
    sheet.build_textboxes()
    _, junctions, buses, _ = sheet.wire()
    sheet.wire_taps()
    crossings = sheet.find_crossings(junctions, sheet.polys)
    return dict(polys=sheet.polys, drawn=sheet.drawn, junctions=junctions,
                buses=buses, crossings=crossings, ports=sheet.abs,
                port_line_types=sheet.port_lt, suction_runs=sheet.suction_runs,
                warnings=sheet.warn, textboxes=sheet.textboxes)


def panel(renderer, intent, layout, catalog):
    with mock.patch.object(optimizer, 'R', renderer):
        return optimizer.bpanel(copy.deepcopy(layout), intent, catalog)


def render(renderer, intent, layout, workdir):
    # JSON is valid YAML 1.2. Serialized copies avoid changing the source files.
    (workdir / '1#系统.intent.yaml').write_text(
        json.dumps(intent, ensure_ascii=False), encoding='utf-8')
    (workdir / '1#系统.layout.json').write_text(
        json.dumps(layout, ensure_ascii=False), encoding='utf-8')
    with contextlib.redirect_stdout(io.StringIO()):
        renderer.main([str(workdir)])
    return (workdir / '1#系统原理图.svg').read_bytes()


def count_work(renderer, cases, catalog):
    counts = dict(hits=0, overlap=0, crossings=0)
    with contextlib.ExitStack() as stack:
        for name in counts:
            original = getattr(renderer.Sheet, name)

            def counted(*args, _name=name, _original=original, **kwargs):
                counts[_name] += 1
                return _original(*args, **kwargs)

            stack.enter_context(mock.patch.object(renderer.Sheet, name,
                                                   staticmethod(counted)))
        for _, intent, layout in cases:
            geometry(renderer, intent, layout, catalog)
    return counts


class RendererDefaultsTest(unittest.TestCase):
    def test_missing_or_null_labels_match_explicit_empty_maps(self):
        # Includes a named user symbol: fill_name_slot also needs the default.
        library = Path(candidate.SKILL_LIB)
        catalog = json.loads((library / 'component-catalog.json').read_text())
        intent = dict(parts={'V-1': 'check_valve', 'U-1': 'hydraulic_user'},
                      paths=[], extern={})
        layout = dict(canvas=dict(width=800, height=600), externs={}, nodes={
            'V-1': dict(x=50, y=100, w=80, h=80, symbol='check-valve.svg'),
            'U-1': dict(x=350, y=100, w=160, h=60, symbol='hydraulic-user.svg')})

        def labels(changed):
            sheet = candidate.Sheet(intent, changed, catalog, cat_dir=str(library))
            sheet.place()
            sheet.build_textboxes()
            return sheet.textboxes, sheet.texts(), sheet.symbols()

        expected = labels(dict(copy.deepcopy(layout), labels={}, label_pos={}))
        self.assertEqual(labels(copy.deepcopy(layout)), expected)
        self.assertEqual(labels(dict(copy.deepcopy(layout), labels=None,
                                     label_pos=None)), expected)

    def test_equal_score_routes_keep_first_candidate(self):
        sheet = candidate.Sheet(dict(parts={}, paths=[]),
                                dict(canvas=dict(width=500, height=500), nodes={}),
                                dict(components=[]))
        self.assertEqual(sheet.route((0, 0, 'right'), (80, 80, 'left')),
                         [(0, 0), (20.0, 0), (60.0, 0),
                          (60.0, 80), (80, 80)])


def differential(baseline, cases, catalog):
    checks = []
    with tempfile.TemporaryDirectory(prefix='hydraulic-route-regression-') as tmp:
        workdir = Path(tmp)
        for name, intent, layout in cases:
            old_geometry = geometry(baseline, intent, layout, catalog)
            new_geometry = geometry(candidate, intent, layout, catalog)
            assert old_geometry == new_geometry, name + ': routed geometry differs'
            old_panel = panel(baseline, intent, layout, catalog)
            new_panel = panel(candidate, intent, layout, catalog)
            assert old_panel == new_panel, name + ': budget/hard-defect metrics differ'
            old_svg = render(baseline, intent, layout, workdir)
            new_svg = render(candidate, intent, layout, workdir)
            assert old_svg == new_svg, name + ': complete SVG bytes differ'
            checks.append(dict(case=name, svg_bytes=len(new_svg),
                               polylines=len(new_geometry['polys']),
                               buses=len(new_geometry['buses']),
                               taps=len(intent.get('taps') or []), panel=new_panel))
        name, intent, layout = cases[0]
        explicit = copy.deepcopy(layout)
        explicit['labels'], explicit['label_pos'] = {}, {}
        old_svg = render(baseline, intent, explicit, workdir)
        missing = copy.deepcopy(layout)
        missing.pop('labels', None)
        missing.pop('label_pos', None)
        assert old_svg == render(candidate, intent, missing, workdir), \
            'missing labels differ from explicit defaults'
    return checks


def benchmark(baseline, cases, catalog):
    # Both modules use equally warm symbol caches. Cache data is read-only.
    for module in (baseline, candidate):
        module.read_symbol = functools.lru_cache(None)(module.read_symbol)
        for _, intent, layout in cases:
            panel(module, intent, layout, catalog)
    rounds = []
    for reverse in (False, True):
        durations = {}
        order = [('baseline', baseline), ('pruned', candidate)]
        if reverse:
            order.reverse()
        for key, module in order:
            start = time.perf_counter()
            for _, intent, layout in cases:
                panel(module, intent, layout, catalog)
            durations[key + '_s'] = time.perf_counter() - start
        durations['speedup'] = durations['baseline_s'] / durations['pruned_s']
        rounds.append(durations)
    return rounds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-script', type=Path)
    parser.add_argument('--repo-root', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RendererDefaultsTest))
    if not result.wasSuccessful():
        return 1
    if not args.baseline_script and not args.repo_root:
        print('Unit tests passed; full differential requires --baseline-script and --repo-root.')
        return 0
    if not args.baseline_script or not args.repo_root:
        parser.error('--baseline-script and --repo-root must be provided together')
    baseline = load_baseline(args.baseline_script.resolve())
    catalog = json.loads(Path(candidate.SKILL_CATALOG).read_text(encoding='utf-8'))
    cases = cases_from_repo(args.repo_root.resolve())
    checks = differential(baseline, cases, catalog)
    old_work = count_work(baseline, cases, catalog)
    new_work = count_work(candidate, cases, catalog)
    assert new_work['crossings'] < old_work['crossings'], \
        'pruning did not avoid any expensive crossing evaluations'
    summary = dict(cases=len(cases), geometry_equal=True, panel_equal=True,
                   full_svg_bytes_equal=True, checks=checks,
                   baseline_calls=old_work, pruned_calls=new_work,
                   timings=benchmark(baseline, cases, catalog))
    if args.report:
        args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                               encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'checks'},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
