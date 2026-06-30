import unittest
import typing as t
from sexpdata import Symbol

from src.coq_serapy_util.feedback import FeedbackMessage, SexpArray


class Test_FeedbackMessage_from_sexp_array(unittest.TestCase):
    def test_message(self):
        sexp: SexpArray = [
            "Feedback",
            [
                ["doc_id", 0],
                ["span_id", 43],
                ["route", 0],
                [
                    "contents",
                    [
                        "Message",
                        ["level", "Info"],
                        ["loc"],
                        [
                            "pp",
                            [
                                "Pp_string",
                                "Replace the hammer tactic with:\n\tqauto use: WF.add_o.",
                            ],
                        ],
                        [
                            "str",
                            "Replace the hammer tactic with:\n\tqauto use: WF.add_o.",
                        ],
                    ],
                ],
            ],
        ]

        expected: FeedbackMessage = FeedbackMessage(
            doc_id=0,
            span_id=43,
            route=0,
            level="Info",
            message="Replace the hammer tactic with:\n\tqauto use: WF.add_o.",
        )

        result = FeedbackMessage.from_sexp_array(sexp)

        self.assertEqual(result, expected)

    def test_message_2(self):
        sexp: SexpArray = [
            "Feedback",
            [
                ["doc_id", 0],
                ["span_id", 1201],
                ["route", 0],
                [
                    "contents",
                    [
                        "Message",
                        ["level", "Info"],
                        ["loc"],
                        [
                            "pp",
                            [
                                "Pp_string",
                                "Replace the hammer tactic with: sfirstorder ",
                            ],
                        ],
                        [
                            "str",
                            "Replace the hammer tactic with: sfirstorder ",
                        ],
                    ],
                ],
            ],
        ]

        expected: FeedbackMessage = FeedbackMessage(
            doc_id=0,
            span_id=1201,
            route=0,
            level="Info",
            message="Replace the hammer tactic with: sfirstorder ",
        )

        result = FeedbackMessage.from_sexp_array(sexp)

        self.assertEqual(result, expected)

    def test_message_3(self):
        sexp: SexpArray = [
            "Feedback",
            [
                ["doc_id", 0],
                ["span_id", 129],
                ["route", 0],
                [
                    "contents",
                    [
                        "Message",
                        ["level", "Info"],
                        ["loc"],
                        [
                            "pp",
                            [
                                "Pp_string",
                                "Replace the hammer tactic with:\n\thauto use: @restrict_agree unfold: node, PositiveMap.key, coloring, nodeset, PositiveOrderedTypeBits.t.",
                            ],
                        ],
                        [
                            "str",
                            "Replace the hammer tactic with:\n\thauto use: @restrict_agree unfold: node, PositiveMap.key, coloring, nodeset, PositiveOrderedTypeBits.t.",
                        ],
                    ],
                ],
            ],
        ]
        expected: FeedbackMessage = FeedbackMessage(
            doc_id=0,
            span_id=129,
            route=0,
            level="Info",
            message="Replace the hammer tactic with:\n\thauto use: @restrict_agree unfold: node, PositiveMap.key, coloring, nodeset, PositiveOrderedTypeBits.t.",
        )

        result = FeedbackMessage.from_sexp_array(sexp)

        self.assertEqual(result, expected)

    def test_message_symbol(self):
        sexp: SexpArray = [
            Symbol("Feedback"),
            [
                [Symbol("doc_id"), 0],
                [Symbol("span_id"), 196],
                [Symbol("route"), 0],
                [
                    Symbol("contents"),
                    [
                        Symbol("Message"),
                        [Symbol("level"), Symbol("Info")],
                        [Symbol("loc"), []],
                        [
                            Symbol("pp"),
                            [
                                Symbol("Pp_string"),
                                "- dependencies: H2, H1, Wigderson.graph.find_in_adj, H3, SerTop.MyModule.restrict_agree_2\n- definitions: FSets.FMapPositive.PositiveMap.key, Structures.OrderedTypeEx.PositiveOrderedTypeBits.t, FSets.FSetPositive.PositiveSet.elt, Wigderson.graph.node",
                            ],
                        ],
                        [
                            Symbol("str"),
                            "- dependencies: H2, H1, Wigderson.graph.find_in_adj, H3, SerTop.MyModule.restrict_agree_2\n- definitions: FSets.FMapPositive.PositiveMap.key, Structures.OrderedTypeEx.PositiveOrderedTypeBits.t, FSets.FSetPositive.PositiveSet.elt, Wigderson.graph.node",
                        ],
                    ],
                ],
            ],
        ]
        expected: FeedbackMessage = FeedbackMessage(
            doc_id=0,
            span_id=196,
            route=0,
            level="Info",
            message="- dependencies: H2, H1, Wigderson.graph.find_in_adj, H3, SerTop.MyModule.restrict_agree_2\n- definitions: FSets.FMapPositive.PositiveMap.key, Structures.OrderedTypeEx.PositiveOrderedTypeBits.t, FSets.FSetPositive.PositiveSet.elt, Wigderson.graph.node",
        )

        result = FeedbackMessage.from_sexp_array(sexp)

        self.assertEqual(result, expected)

    def test_processed(self) -> None:
        # (Feedback((doc_id 0)(span_id 41)(route 0)(contents Processed)))
        sexp: SexpArray = [
            "Feedback",
            [
                ["doc_id", 0],
                ["span_id", 41],
                ["route", 0],
                ["contents", ["Processed"]],
            ],
        ]

        self.assertIsNone(FeedbackMessage.from_sexp_array(sexp))


class Test_FeedbackMessage_hammer_reconstruction_tactic(unittest.TestCase):
    def test_hammer_reconstruction_tactic(self):
        message = FeedbackMessage(
            doc_id=0,
            span_id=43,
            route=0,
            level="Info",
            message="Replace the hammer tactic with:\n\tqauto use: WF.add_o.",
        )

        self.assertEqual(message.hammer_reconstruction_tactic(), "qauto use: WF.add_o.")

    def test_hammer_reconstruction_tactic_no_newline(self):
        message = FeedbackMessage(
            doc_id=0,
            span_id=58,
            route=0,
            level="Info",
            message="Replace the hammer tactic with: sfirstorder ",
        )
        self.assertEqual(message.hammer_reconstruction_tactic(), "sfirstorder.")

    def test_no_hammer_reconstruction_tactic(self):
        message = FeedbackMessage(
            doc_id=0,
            span_id=43,
            route=0,
            level="Info",
            message="This is a normal message.",
        )

        self.assertIsNone(message.hammer_reconstruction_tactic())

    def test_srun(self) -> None:
        message = FeedbackMessage(
            doc_id=0,
            span_id=43,
            route=0,
            level="Info",
            message="Replace the hammer tactic with:\n\tsrun eauto use: find_in_adj unfold: node, PositiveMap.key, PositiveOrderedTypeBits.t. ",
        )

        self.assertEqual(
            message.hammer_reconstruction_tactic(),
            "srun (eauto) use: find_in_adj unfold: node, PositiveMap.key, PositiveOrderedTypeBits.t.",
        )


if __name__ == "__main__":
    unittest.main()
