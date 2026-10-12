"""#23 production bridge registration: the grant binds the current 1# intent.

The single registered policy current-1-verified-single-bridge-20261012 is
bound by content: its intent_sha256 must equal the real bytes of
1#系统原理图/1#系统.intent.yaml (re-hashed here independently), the
production layout must explicitly select that policy id, and check_bridge_
policy must grant allowance 1 on the real files. Any intent edit without
re-registration, or a layout silently dropping the selection, fails here.
The skill-side portable copy of the registry-shape assertions lives in
scripts/test_bridge_allowance.py.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from repository_context import REPO, SKILL

import bridge_allowance as BA

POLICY_ID = 'current-1-verified-single-bridge-20261012'
SHEET = REPO / '1#系统原理图'
INTENT = SHEET / '1#系统.intent.yaml'
LAYOUT = SHEET / '1#系统.layout.json'


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


class BridgeRegistration(unittest.TestCase):

    def test_registered_digest_matches_the_real_intent_bytes(self):
        # 登记与真实文件字节对账：intent 漂移未重登记即失败（fail-closed）。
        entry = BA.PRODUCTION_BRIDGE_POLICIES[POLICY_ID]
        self.assertEqual(entry['intent_sha256'], _file_sha256(INTENT),
                         '1#系统.intent.yaml 内容已变，#23 跳线登记失效，'
                         '须按新内容重新登记')
        self.assertEqual(
            (REPO / entry['intent_path']).resolve(), INTENT.resolve(),
            '登记记录的 intent 路径必须指向真实被绑定的文件')

    def test_production_layout_selects_the_registered_policy(self):
        # 许可须由布局显式选择，不按文件名/标题放行；静默丢字段不算选择。
        layout = json.loads(LAYOUT.read_text(encoding='utf-8'))
        self.assertEqual(layout.get('bridge_policy'), POLICY_ID)
        for key in BA.FORBIDDEN_LAYOUT_KEYS:
            self.assertNotIn(key, layout)

    def test_real_files_grant_exactly_one_verified_bridge(self):
        granted = BA.check_bridge_policy(
            json.loads(LAYOUT.read_text(encoding='utf-8')), str(INTENT))
        self.assertEqual(granted['policy_id'], POLICY_ID)
        self.assertEqual(granted['allowance'], 1)
        self.assertEqual(granted['intent_sha256'], _file_sha256(INTENT))
        self.assertIn('#23', granted['decision'])

    def test_tampered_intent_copy_invalidates_the_binding(self):
        with tempfile.TemporaryDirectory(prefix='bridge-reg-') as raw:
            copy = Path(raw) / '1#系统.intent.yaml'
            copy.write_bytes(INTENT.read_bytes() + b'# drifted\n')
            layout = json.loads(LAYOUT.read_text(encoding='utf-8'))
            with self.assertRaises(ValueError) as ctx:
                BA.check_bridge_policy(layout, str(copy))
            message = str(ctx.exception)
            self.assertIn(POLICY_ID, message)
            self.assertIn('失效', message)
            self.assertIn(_file_sha256(copy), message)

    def test_registry_has_no_other_grants(self):
        # 生产登记现状：恰好一条政策（#23 定案），其他图纸默认 0。
        self.assertEqual(set(BA.PRODUCTION_BRIDGE_POLICIES), {POLICY_ID})
        self.assertEqual(
            BA.PRODUCTION_BRIDGE_POLICIES[POLICY_ID]
            ['maximum_verified_bridges'], 1)


if __name__ == '__main__':
    unittest.main()
