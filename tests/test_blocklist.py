# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for the blocklist script. Run with: python3 -m unittest discover tests"""

import importlib.machinery
import importlib.util
import ipaddress
import os
import tempfile
import textwrap
import time
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), os.pardir, "blocklist")
_loader = importlib.machinery.SourceFileLoader("blocklist", SCRIPT)
_spec = importlib.util.spec_from_loader("blocklist", _loader)
bl = importlib.util.module_from_spec(_spec)
_loader.exec_module(bl)

net = ipaddress.ip_network


class ParserTest(unittest.TestCase):
    def test_plain(self):
        text = "﻿# header\n1.2.3.4\n5.6.7.0/24 ; SBL123\n\n  9.9.9.9  extra\n"
        self.assertEqual(list(bl.parse_plain(text)), ["1.2.3.4", "5.6.7.0/24", "9.9.9.9"])

    def test_spamhaus_json(self):
        text = ('{"cidr":"2a00:4c80::/29","sblid":"SBL1","rir":"ripencc"}\n'
                '{"type":"metadata","timestamp":1,"records":1}\n')
        self.assertEqual(list(bl.parse_spamhaus_json(text)), ["2a00:4c80::/29"])

    def test_dshield(self):
        text = ("# comment\nStart\tEnd\tNetblock\tAttacks\n"
                "64.62.156.0\t64.62.156.255\t24\t347\tHURRICANE\tUS\tabuse@he.net\n")
        self.assertEqual(list(bl.parse_dshield(text)), ["64.62.156.0/24"])

    def test_fmt_drops_host_prefix(self):
        self.assertEqual(bl.fmt(net("1.2.3.4/32")), "1.2.3.4")
        self.assertEqual(bl.fmt(net("2001:db8::1/128")), "2001:db8::1")
        self.assertEqual(bl.fmt(net("1.2.3.0/24")), "1.2.3.0/24")


class FilterTest(unittest.TestCase):
    def test_subtract_splits_around_protected(self):
        parts = bl.subtract(net("1.1.0.0/16"), [net("1.1.1.1/32")])
        self.assertNotIn(net("1.1.1.1/32"), parts)
        self.assertFalse(any(p.overlaps(net("1.1.1.1/32")) for p in parts))
        self.assertEqual(sum(p.num_addresses for p in parts), 65535)

    def test_subtract_drops_contained(self):
        self.assertEqual(bl.subtract(net("10.1.2.3/32"), [net("10.0.0.0/8")]), [])

    def test_subtract_ignores_other_family(self):
        self.assertEqual(bl.subtract(net("1.2.3.4/32"), [net("::1/128")]), [net("1.2.3.4/32")])

    def test_remove_covered(self):
        nets = [net("1.2.3.0/24"), net("1.2.3.4/32"), net("1.2.4.4/32"), net("1.2.4.5/32")]
        # adjacent addresses are kept apart, only covered ones are dropped
        self.assertEqual(sorted(bl.remove_covered(nets)),
                         [net("1.2.3.0/24"), net("1.2.4.4/32"), net("1.2.4.5/32")])


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.spool = os.path.join(d, "spool")
        self.out = os.path.join(d, "out", "iplist.txt")
        self.marker = os.path.join(d, "published")
        os.makedirs(self.spool)
        os.makedirs(os.path.dirname(self.out))
        self.src = os.path.join(d, "source.txt")
        self.conf = os.path.join(d, "blocklists.conf")
        with open(self.conf, "w") as f:
            f.write(textwrap.dedent(f"""\
                [global]
                spool_dir = {self.spool}
                output = {self.out}
                post_publish = /usr/bin/touch {self.marker}
                never_block = 1.1.1.1
                max_shrink_percent = 30
                default_min_entries = 2

                [test]
                url = file://{self.src}

                [other]
                url = file://{self.src}
                """))
        self.cfg = bl.Config(self.conf)

    def tearDown(self):
        self.tmp.cleanup()

    def write_source(self, text):
        with open(self.src, "w") as f:
            f.write(text)

    def write_spool(self, name, lines, age_days=0):
        path = self.cfg.spool_file(name)
        with open(path, "w") as f:
            f.write("".join(l + "\n" for l in lines))
        t = time.time() - age_days * 86400
        os.utime(path, (t, t))

    def read_output(self):
        with open(self.out) as f:
            return f.read().split()

    def test_fetch_stores_normalized_entries(self):
        self.write_source("# list\n1.2.3.4/32\n1.2.3.4\n5.6.7.0/24\n")
        self.assertEqual(bl.cmd_fetch(self.cfg, "test"), 0)
        with open(self.cfg.spool_file("test")) as f:
            self.assertEqual(f.read().split(), ["1.2.3.4", "5.6.7.0/24"])

    def test_fetch_keeps_previous_list_on_garbage(self):
        self.write_spool("test", ["1.2.3.4", "5.6.7.8"])
        self.write_source("<html>\n<body>rate limited</body>\n</html>\n")
        self.assertEqual(bl.cmd_fetch(self.cfg, "test"), 1)
        with open(self.cfg.spool_file("test")) as f:
            self.assertEqual(f.read().split(), ["1.2.3.4", "5.6.7.8"])

    def test_assemble_filters_and_publishes(self):
        self.write_spool("test", ["1.2.3.4", "10.0.0.1", "0.0.0.0/1", "2001:db8::1",
                                  "2a00:4c80::/29", "1.1.1.0/30"])
        self.write_spool("other", ["1.2.3.0/24", "9.9.9.9"])
        self.assertEqual(bl.cmd_assemble(self.cfg, force=False), 0)
        # private, too broad, documentation and covered entries are gone,
        # the range holding the never_block address is split around it
        self.assertEqual(self.read_output(), ["1.1.1.0", "1.1.1.2/31", "1.2.3.0/24",
                                              "9.9.9.9", "2a00:4c80::/29"])
        self.assertTrue(os.path.exists(self.marker))

    def test_assemble_unchanged_skips_post_publish(self):
        self.write_spool("test", ["1.2.3.4", "5.6.7.8"])
        bl.cmd_assemble(self.cfg, force=False)
        os.unlink(self.marker)
        self.assertEqual(bl.cmd_assemble(self.cfg, force=False), 0)
        self.assertFalse(os.path.exists(self.marker))

    def test_assemble_leaves_out_stale_sources(self):
        self.write_spool("test", ["1.2.3.4", "5.6.7.8"])
        self.write_spool("other", ["9.9.9.9"], age_days=10)
        bl.cmd_assemble(self.cfg, force=False)
        self.assertEqual(self.read_output(), ["1.2.3.4", "5.6.7.8"])

    def test_assemble_shrink_guard(self):
        self.write_spool("test", [f"1.2.3.{i}" for i in range(1, 11)])
        bl.cmd_assemble(self.cfg, force=False)
        self.write_spool("test", ["1.2.3.1"])
        self.assertEqual(bl.cmd_assemble(self.cfg, force=False), 1)
        self.assertEqual(len(self.read_output()), 10)
        self.assertEqual(bl.cmd_assemble(self.cfg, force=True), 0)
        self.assertEqual(self.read_output(), ["1.2.3.1"])

    def test_post_publish_output_is_an_error(self):
        self.cfg.post_publish = "/bin/echo something went wrong"
        self.write_spool("test", ["1.2.3.4", "5.6.7.8"])
        self.assertEqual(bl.cmd_assemble(self.cfg, force=False), 1)


if __name__ == "__main__":
    unittest.main()
