"""Tests for sysml_parser (narrow SysML syntax layer).

Run from the repository root:
    python -m unittest discover -s .agents/skills/hydraulic-schematic/scripts -p test_sysml_parser.py -v
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sysml_parser as sp

FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "assets", "fixtures", "sysml-l0", "blocked-project.sysml")


def read_fixture():
    with open(FIXTURE, "r", encoding="utf-8") as fh:
        return fh.read()


def line_of(text, needle):
    """1-based line of the first occurrence of *needle* in *text*."""
    return text[:text.index(needle)].count("\n") + 1


class MinimalPositiveTest(unittest.TestCase):
    def test_package_part_def_ports(self):
        model = sp.parse("package 'P' {\n"
                         "  part def 'A' {\n"
                         "    port 'in';  // upstream\n"
                         "    port 'out';\n"
                         "  }\n"
                         "}\n")
        pkg = model.packages[0]
        self.assertEqual(pkg.name, "P")
        self.assertEqual(pkg.line, 1)
        self.assertEqual(len(pkg.parts), 1)
        adef = pkg.parts[0]
        self.assertEqual((adef.name, adef.kind, adef.type_ref), ("A", "def", None))
        self.assertEqual(adef.line, 2)
        self.assertEqual([p.name for p in adef.ports], ["in", "out"])
        self.assertEqual(adef.ports[0].line, 3)
        self.assertEqual([c.text for c in model.comments if c.kind == "line"], ["upstream"])

    def test_part_def_terminated_by_semicolon(self):
        model = sp.parse("part def 'A';")
        self.assertEqual(model.parts[0].kind, "def")
        self.assertEqual(model.parts[0].ports, [])

    def test_typed_instance_part_and_system_part(self):
        model = sp.parse("part 'SYS' {\n"
                         "  part 'i1' : 'A';\n"
                         "  connect 'i1'.'p' to 'i2';\n"
                         "  part 'i2' : 'B';\n"
                         "}\n")
        syspart = model.parts[0]
        self.assertEqual(syspart.kind, "system")
        self.assertIsNone(syspart.type_ref)
        self.assertEqual([p.name for p in syspart.parts], ["i1", "i2"])
        self.assertEqual(syspart.parts[0].type_ref, ["A"])
        self.assertEqual(syspart.parts[1].type_ref, ["B"])
        self.assertEqual(syspart.connects[0].source.segments, ["i1", "p"])
        self.assertEqual(syspart.connects[0].target.segments, ["i2"])
        self.assertEqual(syspart.connects[0].line, 3)

    def test_multiple_top_level_definitions(self):
        model = sp.parse("package 'P' { }\npart def 'A';\npart 'S' { }\n")
        self.assertEqual(len(model.packages), 1)
        self.assertEqual(len(model.parts), 2)

    def test_same_name_across_scopes_is_legal(self):
        model = sp.parse("package 'P' {\n"
                         "  part def 'x' { port 'x'; }\n"   # 'x': package scope (def) and its body scope (port)
                         "  part 'S' { part 'x' : 'x'; }\n"  # 'x': S body scope (instance), typed by def 'x'
                         "}\n")
        pkg = model.packages[0]
        self.assertEqual(pkg.parts[0].name, "x")
        self.assertEqual(pkg.parts[0].ports[0].name, "x")
        system = pkg.parts[1]
        self.assertEqual(system.parts[0].name, "x")
        self.assertEqual(system.parts[0].type_ref, ["x"])
        # ... while a literal repeat in one scope is still rejected
        with self.assertRaises(sp.SysmlParseError):
            sp.parse("package 'P' {\n part def 'x';\n part 'x' : 'T';\n}")

    def test_nested_package(self):
        model = sp.parse("package 'outer' { package 'inner' { part def 'A'; } }")
        self.assertEqual(model.packages[0].packages[0].name, "inner")

    def test_multiline_whitespace_and_block_comments(self):
        model = sp.parse("/* header\nspanning lines */\npart\n\n def 'A'\n{\n port 'p'\n ;\n}\n")
        self.assertEqual(model.parts[0].name, "A")
        block = [c for c in model.comments if c.kind == "block"][0]
        self.assertEqual((block.line, block.end_line), (1, 2))

    def test_comment_markers_inside_quoted_names(self):
        model = sp.parse("part def 'a//b' { port 'x/*y*/z'; } // real comment\n")
        self.assertEqual(model.parts[0].name, "a//b")
        self.assertEqual(model.parts[0].ports[0].name, "x/*y*/z")
        self.assertEqual(len(model.comments), 1)
        self.assertEqual(model.comments[0].text, "real comment")

    def test_block_comment_marker_sequence_inside_line_comment(self):
        model = sp.parse("// not closed /* ever\npart def 'A';\n")
        self.assertEqual(len(model.parts), 1)
        self.assertEqual(model.comments[0].kind, "line")

    def test_quoted_keyword_spellings_are_plain_names(self):
        model = sp.parse("part 'def' : 'T';\n"
                         "part 'part' {\n"
                         "  port 'port';\n"
                         "  port 'to';\n"
                         "}\n")
        self.assertEqual(model.parts[0].name, "def")
        self.assertEqual(model.parts[0].kind, "instance")
        self.assertEqual(model.parts[0].type_ref, ["T"])
        system = model.parts[1]
        self.assertEqual((system.name, system.kind), ("part", "system"))
        self.assertEqual([p.name for p in system.ports], ["port", "to"])

    def test_quoted_keyword_names_in_defs_and_endpoints(self):
        model = sp.parse("part def 'def' { port 'connect'; }\n"
                         "part 'S' {\n"
                         "  connect 'to' to 'to';\n"
                         "  connect 'a'.'to' to 'def'.'connect';\n"
                         "}\n")
        self.assertEqual(model.parts[0].name, "def")
        self.assertEqual(model.parts[0].ports[0].name, "connect")
        c1, c2 = model.parts[1].connects
        self.assertEqual((c1.source.segments, c1.target.segments), (["to"], ["to"]))
        self.assertEqual((c2.source.segments, c2.target.segments),
                         (["a", "to"], ["def", "connect"]))

    def test_bare_to_still_separates_endpoints_with_quoted_to_names(self):
        model = sp.parse("part 'S' { connect 'to'.'to' to 'x'; }")
        conn = model.parts[0].connects[0]
        self.assertEqual(conn.source.segments, ["to", "to"])
        self.assertEqual(conn.target.segments, ["x"])


class NegativeSyntaxTest(unittest.TestCase):
    def assert_error(self, text, expected_line=None):
        with self.assertRaises(sp.SysmlParseError) as cm:
            sp.parse(text)
        if expected_line is not None:
            self.assertEqual(cm.exception.line, expected_line)
        self.assertIn("line ", str(cm.exception))
        return cm.exception

    def test_unknown_syntax(self):
        self.assert_error("foo 'bar';", 1)

    def test_typed_part_with_body_is_not_in_grammar(self):
        self.assert_error("part 'a' : 'T' { }", 1)

    def test_dangling_token_after_model(self):
        self.assert_error("package 'P' { } }", 1)

    def test_missing_semicolon_then_next_statement(self):
        self.assert_error("package 'P' {\n part 'x' : 'T'\n port 'y';\n}", 3)

    def test_multi_element_connect_rejected(self):
        self.assert_error("part 'S' { connect 'a' to 'b' to 'c'; }", 1)

    def test_unterminated_quoted_name(self):
        self.assert_error("part 'abc", 1)

    def test_unterminated_quoted_name_reports_current_line(self):
        self.assert_error("part def 'A';\nport 'broken\n", 2)

    def test_unterminated_block_comment(self):
        self.assert_error("/* never closed\npart def 'A';", 1)

    def test_unterminated_package_brace(self):
        err = self.assert_error("package 'P' {")
        self.assertIn("unterminated", str(err))

    def test_unterminated_part_brace(self):
        self.assert_error("part 'S' {\n connect 'a' to 'b';\n", 3)

    def test_duplicate_port_in_same_scope(self):
        err = self.assert_error("part def 'A' {\n port 'x';\n port 'x';\n}", 3)
        self.assertIn("duplicate", str(err))

    def test_duplicate_part_in_same_scope(self):
        self.assert_error("part 'S' { part 'i' : 'A'; part 'i' : 'B'; }", 1)

    def test_duplicate_part_def_in_same_scope(self):
        self.assert_error("package 'P' { part def 'A'; part def 'A'; }", 1)

    def test_port_and_part_conflict_in_same_scope(self):
        err = self.assert_error("part def 'A' { port 'x'; part 'x' : 'T'; }", 1)
        self.assertIn("duplicate", str(err))

    def test_duplicate_package_in_same_scope(self):
        self.assert_error("package 'P' { }\npackage 'P' { }", 2)

    def test_dangling_dot_in_endpoint(self):
        self.assert_error("part 'S' { connect 'a'. to 'b'; }", 1)

    def test_connect_missing_to(self):
        self.assert_error("part 'S' { connect 'a' 'b'; }", 1)

    def test_unexpected_character(self):
        self.assert_error("part def 'A' @ ;", 1)

    def test_quoted_part_is_not_a_keyword(self):
        self.assert_error("'part' def 'T';", 1)

    def test_quoted_to_cannot_replace_the_connect_keyword(self):
        self.assert_error("part 'S' { connect 'a' 'to' 'b'; }", 1)

    def test_quoted_def_is_a_name_not_the_def_keyword(self):
        # 'def' quoted is consumed as the part *name*; the bare 'x' then dangles.
        self.assert_error("part 'def' 'x';", 1)

    def test_bare_def_inside_part_body_is_rejected(self):
        self.assert_error("part 'S' { def 'x' : 'T'; }", 1)


class BlockedProjectFixtureTest(unittest.TestCase):
    """The verbatim copy of 1#系统原理图/1#系统.sysml at the syntax layer only.

    Passing these tests says nothing about semantic convertibility of the
    full model; it validates the parser against the real narrow-grammar text.
    """

    @classmethod
    def setUpClass(cls):
        cls.text = read_fixture()
        cls.model = sp.parse(cls.text)

    def find_part(self, name):
        for pkg in self.model.packages:
            for part in pkg.parts:
                if part.name == name:
                    return part
        self.fail("part {!r} not found".format(name))

    def test_package_location_and_name(self):
        self.assertEqual(len(self.model.packages), 1)
        pkg = self.model.packages[0]
        self.assertEqual(pkg.name, "HYD-SYS-1")
        self.assertEqual(pkg.line, line_of(self.text, "package 'HYD-SYS-1'"))
        self.assertEqual(pkg.line, 32)

    def test_part_defs_and_system_part(self):
        pkg = self.model.packages[0]
        defs = [p for p in pkg.parts if p.kind == "def"]
        systems = [p for p in pkg.parts if p.kind == "system"]
        self.assertEqual(len(defs), 23)
        self.assertEqual(len(systems), 1)
        self.assertEqual(systems[0].name, "HYD-SYS-1")
        self.assertEqual(systems[0].line, line_of(self.text, "part 'HYD-SYS-1' {"))
        self.assertEqual(systems[0].line, 214)

    def test_system_has_29_instances_and_40_connects(self):
        system = self.find_part("HYD-SYS-1")
        self.assertEqual(len(system.parts), 29)
        self.assertTrue(all(p.kind == "instance" and p.type_ref for p in system.parts))
        self.assertEqual(len(system.connects), 40)

    def test_system_instance_types_and_lines(self):
        system = self.find_part("HYD-SYS-1")
        by_name = {p.name: p for p in system.parts}
        tank = by_name["TANK-001"]
        self.assertEqual(tank.type_ref, ["bootstrap_reservoir"])
        self.assertEqual(tank.line, line_of(self.text, "part 'TANK-001'"))
        self.assertEqual(tank.line, 219)
        users = [p for p in system.parts if p.type_ref == ["hydraulic_user"]]
        self.assertEqual(len(users), 8)

    def test_internal_connects_do_not_leak_into_system(self):
        pkg = self.model.packages[0]
        system = self.find_part("HYD-SYS-1")
        internal = []
        for part in pkg.parts:
            if part.kind == "def":
                internal.extend((tuple(c.source.segments), tuple(c.target.segments))
                                for c in part.connects)
        system_pairs = {(tuple(c.source.segments), tuple(c.target.segments))
                        for c in system.connects}
        self.assertEqual(len(internal), 19)
        self.assertEqual(system_pairs & set(internal), set())
        # every system connect endpoint root is a declared system instance
        instance_names = {p.name for p in system.parts}
        for conn in system.connects:
            self.assertIn(conn.source.segments[0], instance_names)
            self.assertIn(conn.target.segments[0], instance_names)

    def test_internal_connect_stays_inside_its_def(self):
        body = self.find_part("filter_line_shutoff_dp")
        self.assertEqual(len(body.connects), 4)
        first = body.connects[0]
        self.assertEqual(first.source.segments, ["inlet"])
        self.assertEqual(first.target.segments, ["element", "inlet"])
        self.assertEqual(first.line, line_of(self.text,
                                             "connect 'inlet' to 'element'.'inlet';"))

    def test_port_declaration_lines(self):
        body = self.find_part("bootstrap_reservoir")
        self.assertEqual([p.name for p in body.ports],
                         ["suction_out", "return_in", "bootstrap_pressure_in"])
        self.assertEqual(body.ports[0].line, line_of(self.text, "port 'suction_out';"))
        self.assertEqual(body.ports[0].line, 38)

    def test_comment_table_preserves_text_and_lines(self):
        comments = self.model.comments
        self.assertTrue(comments)
        first = comments[0]
        self.assertEqual(first.kind, "block")
        self.assertEqual(first.line, 1)
        self.assertIn("HYD-SYS-1 拓扑模型", first.text)
        line_comment = [c for c in comments
                        if c.kind == "line" and "吸油出" in c.text][0]
        self.assertEqual(line_comment.line, line_of(self.text, "// 吸油出"))
        self.assertEqual(line_comment.line, 38)
        # a deep interior comment keeps its own line number
        deep = [c for c in comments if "刹" in c.text and c.kind == "line"]
        self.assertTrue(deep)
        for c in deep:
            self.assertEqual(c.text, self.text.splitlines()[c.line - 1].split("//", 1)[1].strip())

    def test_source_lines_are_traceable_for_a_sample_connect(self):
        system = self.find_part("HYD-SYS-1")
        conn = system.connects[0]
        self.assertEqual(conn.line, line_of(self.text,
                                            "connect 'TANK-001'.'suction_out' to 'EMP-001'.'suction';"))
        self.assertEqual(conn.line, 250)
        self.assertEqual(conn.source.segments, ["TANK-001", "suction_out"])
        self.assertEqual(conn.target.segments, ["EMP-001", "suction"])

    def test_fixture_is_the_frozen_blocked_model(self):
        """The fixture is a byte-for-byte frozen copy of the blocked original
        model (1#系统原理图/1#系统.sysml at the time of recording). The test
        tree must stay self-contained (no reads outside the skill), so the
        identity of that frozen snapshot is pinned by SHA256 instead of
        re-reading the project file. Semantic assertions above run against
        this same fixture."""
        with open(FIXTURE, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(
            digest, "08e9fd67f75c7ef4b6b1b20288cb814712868d2643ca122e8e25a44a26f0aeb9")


if __name__ == "__main__":
    unittest.main()
