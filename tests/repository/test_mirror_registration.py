"""#63 production mirror registration: both catalogs permit only the two pumps.

The canonical skill catalog and the 1# project catalog each register
engine_driven_pump / electric_motor_driven_pump for axes x/y, each bound to
its own symbol bytes and port contract (check_mirror re-hashes the real
file, so a stale or copy-pasted digest fails here). Every other component
type must stay denied by default. The skill-side portable copy of this
assertion (canonical catalog only) lives in scripts/test_mirror_policy.py.
"""
import json
import unittest

from repository_context import REPO, SKILL

import mirror_policy as mp

CANONICAL = SKILL / 'assets' / 'component-library'
PROJECT = REPO / '1#系统原理图'
PUMPS = {'engine_driven_pump', 'electric_motor_driven_pump'}
CATALOGS = (CANONICAL, PROJECT)


def _entries(catalog_dir):
    catalog = json.loads(
        (catalog_dir / 'component-catalog.json').read_text(encoding='utf-8'))
    return {c['component_type']: c for c in catalog['components']}


class MirrorRegistration(unittest.TestCase):

    def test_only_the_two_pumps_carry_mirror_permission(self):
        for catalog in CATALOGS:
            entries = _entries(catalog)
            enabled = {ctype for ctype, entry in entries.items()
                       if entry.get('mirror_safe') is True}
            self.assertEqual(enabled, PUMPS, (catalog, sorted(enabled)))

    def test_registered_pumps_pass_check_mirror_on_their_own_assets(self):
        # 各目录用自身登记对自身符号实文件过闸:两目录符号仅行尾字节
        # 不同,摘要各自绑定——一侧共用另一侧的 hash 会在本测试暴露。
        for catalog in CATALOGS:
            entries = _entries(catalog)
            for ctype in sorted(PUMPS):
                entry = entries[ctype]
                asset = catalog / entry['symbol']['asset']
                self.assertTrue(asset.is_file(), asset)
                self.assertEqual(entry['mirror_registration']['axes'],
                                 ['x', 'y'])
                for axis in ('x', 'y'):
                    with self.subTest(catalog=catalog.name, ctype=ctype,
                                      axis=axis):
                        self.assertEqual(
                            mp.check_mirror({'mirror': axis}, entry,
                                            str(asset)),
                            axis)

    def test_every_other_type_is_denied_by_default(self):
        for catalog in CATALOGS:
            entries = _entries(catalog)
            for ctype, entry in sorted(entries.items()):
                if ctype in PUMPS:
                    continue
                asset = catalog / entry['symbol']['asset']
                with self.subTest(catalog=catalog.name, ctype=ctype):
                    with self.assertRaises(ValueError):
                        mp.check_mirror({'mirror': 'x'}, entry, str(asset))


if __name__ == '__main__':
    unittest.main()
