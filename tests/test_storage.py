# Run: python3 -m unittest discover -s tests -v
import json
import os
import random
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(REPO, "main")
sys.path.insert(0, MAIN)

from module.storage import ReadingBuffer  # noqa: E402

WRITER = """
import sys
sys.path.insert(0, sys.argv[2])
from module.storage import ReadingBuffer
b = ReadingBuffer(sys.argv[1])
i = 0
while True:
    seq = b.append({"i": i, "pad": "x" * 500})
    print(seq, flush=True)
    i += 1
"""


class ReadingBufferTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "buffer.db")

    def test_append_oldest_delete(self):
        b = ReadingBuffer(self.db)
        seqs = [b.append({"n": n}) for n in range(5)]
        batch = b.oldest(3)
        self.assertEqual([e["n"] for _, e in batch], [0, 1, 2])
        b.delete_through(batch[-1][0])
        self.assertEqual(b.count(), 2)
        self.assertEqual(b.oldest(10)[0][0], seqs[3])

    def test_seq_never_reused(self):
        b = ReadingBuffer(self.db)
        last = b.append({})
        b.delete_through(last)
        self.assertGreater(b.append({}), last)

    def test_legacy_import(self):
        with open(os.path.join(self.dir, "temporary_device_data.json"), "w") as f:
            json.dump([{"timestamp": "a"}, {"timestamp": "b"}], f)
        with open(os.path.join(self.dir, "broken.json"), "w") as f:
            f.write('[{"timestamp": "half')
        b = ReadingBuffer(self.db)
        b.import_legacy_json(self.dir)
        self.assertEqual([e["timestamp"] for _, e in b.oldest(10)], ["a", "b"])
        self.assertTrue(os.path.exists(os.path.join(self.dir, "temporary_device_data.json.imported")))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "broken.json.corrupt")))
        b.import_legacy_json(self.dir)  # nothing imported twice
        self.assertEqual(b.count(), 2)

    def test_killed_writer_loses_nothing_committed(self):
        """SIGKILL a writer at random moments; every seq it reported as
        committed must still be there, with no gaps and a clean database."""
        for _ in range(5):
            p = subprocess.Popen(
                [sys.executable, "-c", WRITER, self.db, MAIN],
                stdout=subprocess.PIPE, text=True,
            )
            time.sleep(random.uniform(0.3, 1.5))
            p.send_signal(signal.SIGKILL)
            out, _ = p.communicate()
            reported = [int(line) for line in out.split()]

            conn = sqlite3.connect(self.db)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            seqs = [r[0] for r in conn.execute("SELECT seq FROM readings ORDER BY seq")]
            conn.close()
            self.assertTrue(set(reported) <= set(seqs), "a committed entry was lost")
            self.assertEqual(seqs, list(range(1, len(seqs) + 1)), "gap in seq")


if __name__ == "__main__":
    unittest.main()
