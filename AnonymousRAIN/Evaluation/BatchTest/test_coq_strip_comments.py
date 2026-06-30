"""Tests for Coq comment stripping used in batch evaluation."""

from __future__ import annotations

import unittest

from BatchTest.coq_strip_comments import strip_coq_comments


class TestCoqStripComments(unittest.TestCase):
    def test_preserves_notation_scope_percent_ident(self) -> None:
        line = "  wp E t' (f i)%T (fun _ _ => Q i)) -"
        out = strip_coq_comments(line)
        self.assertIn("%T", out)
        self.assertIn("(f i)%T", out)

    def test_strips_line_comment_after_percent_space(self) -> None:
        line = "  intros x. % debug note"
        out = strip_coq_comments(line)
        self.assertEqual(out.strip(), "intros x.")

    def test_block_comment_removed(self) -> None:
        text = "Lemma foo : True. (* hint *) Proof. Qed."
        out = strip_coq_comments(text)
        self.assertNotIn("hint", out)
        self.assertIn("Lemma foo", out)


if __name__ == "__main__":
    unittest.main()
