# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests of the bash completion in completions/blocklist."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
SCRIPT = os.path.join(ROOT, "blocklist")
COMPLETION = os.path.join(ROOT, "completions", "blocklist")


def complete(*words, config=os.devnull):
    """The candidates bash offers for the last of words, which may be empty."""
    words = ("blocklist",) + words
    script = 'source "$1"; shift; COMP_WORDS=("$@"); COMP_CWORD=$(($# - 1)); ' \
             '_blocklist; printf "%s\\n" "${COMPREPLY[@]}"'
    env = dict(os.environ, BLOCKLIST_CONFIG=config)
    result = subprocess.run(["bash", "-c", script, "bash", COMPLETION] + list(words),
                            stdout=subprocess.PIPE, universal_newlines=True, check=True, env=env)
    return [line for line in result.stdout.split("\n") if line]


def help_words():
    """The commands and options the help lists."""
    result = subprocess.run([sys.executable, SCRIPT, "--help"], stdout=subprocess.PIPE,
                            universal_newlines=True, check=True)
    words = set()
    for line in result.stdout.split("\n"):
        match = re.match(r"  blocklist (\S+)", line)
        if match:
            words.update(match.group(1).split("|"))
    return words


@unittest.skipUnless(shutil.which("bash"), "bash is not installed")
class CompletionTests(unittest.TestCase):
    def test_syntax(self):
        subprocess.run(["bash", "-n", COMPLETION], check=True)

    def test_offers_exactly_the_commands_and_options_of_help(self):
        self.assertEqual(set(complete("")), help_words())

    def test_command_prefix(self):
        self.assertEqual(complete("f"), ["fetch"])
        self.assertEqual(complete("--v"), ["--version"])

    def test_fetch_offers_the_sources_of_the_config(self):
        with tempfile.NamedTemporaryFile("w", suffix=".conf") as f:
            f.write(textwrap.dedent("""\
                [global]
                spool_dir = /tmp
                [spamhaus-drop]
                url = https://example.org/a
                [spamhaus-drop-v6]
                url = https://example.org/b
                [dshield]
                url = https://example.org/c
                """))
            f.flush()
            self.assertEqual(sorted(complete("fetch", "", config=f.name)),
                             ["dshield", "spamhaus-drop", "spamhaus-drop-v6"])
            self.assertEqual(complete("fetch", "sp", config=f.name),
                             ["spamhaus-drop", "spamhaus-drop-v6"])
            self.assertEqual(complete("fetch", "dshield", "", config=f.name), [])

    def test_fetch_without_readable_config(self):
        self.assertEqual(complete("fetch", "", config="/nonexistent/blocklists.conf"), [])

    def test_assemble(self):
        self.assertEqual(complete("assemble", ""), ["--force"])
        self.assertEqual(complete("assemble", "--force", "--f"), ["--force"])

    def test_sample_config(self):
        sources = complete("fetch", "", config=os.path.join(ROOT, "blocklists.conf"))
        self.assertIn("abuseipdb", sources)
        self.assertNotIn("global", sources)

    def test_unknown_command(self):
        self.assertEqual(complete("bogus", ""), [])


class VersionTests(unittest.TestCase):
    def test_version(self):
        result = subprocess.run([sys.executable, SCRIPT, "--version"], stdout=subprocess.PIPE,
                                universal_newlines=True, check=True)
        self.assertRegex(result.stdout.strip(), r"^blocklist \d+(\.\d+)+$")

    def test_usage_error(self):
        result = subprocess.run([sys.executable, SCRIPT], stderr=subprocess.PIPE,
                                universal_newlines=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("blocklist fetch", result.stderr)


if __name__ == "__main__":
    unittest.main()
