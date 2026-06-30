from dataclasses import dataclass, field
from sexpdata import Symbol
import typing as t
import re

SexpArray = t.Union[str, int, Symbol, t.List["SexpArray"]]


HAMMER_RECONSTRUCTION_REGEX = re.compile("^Replace the hammer tactic with:\\s+(.*)$")
SRUN_REGEX = re.compile("^(srun) ([a-zA-Z0-9]+) (.*)$")


@dataclass(frozen=True)
class FeedbackMessage:
    doc_id: int
    span_id: int
    route: int
    level: str
    message: str

    def hammer_reconstruction_tactic(self) -> t.Optional[str]:
        match = HAMMER_RECONSTRUCTION_REGEX.match(self.message)
        if not match:
            return None
        ans = match.group(1).strip()
        if not ans.endswith("."):
            ans += "."

        match = SRUN_REGEX.match(ans)
        if match is not None:
            ans = f"{match.group(1)} ({match.group(2)}) {match.group(3)}"
        return ans

    @staticmethod
    def from_sexp_array(sexp: SexpArray) -> t.Optional["FeedbackMessage"]:
        sexp = walk_and_make_symbols_string(sexp)
        try:
            assert isinstance(sexp, list)
            assert len(sexp) == 2

            assert sexp[0] == "Feedback"

            body = sexp[1]
            assert isinstance(body, list)
            assert len(body) == 4

            doc_id_pair = body[0]
            assert isinstance(doc_id_pair, list)
            assert len(doc_id_pair) == 2
            assert doc_id_pair[0] == "doc_id"
            assert isinstance(doc_id_pair[1], int)
            doc_id = doc_id_pair[1]

            span_id_pair = body[1]
            assert isinstance(span_id_pair, list)
            assert len(span_id_pair) == 2
            assert span_id_pair[0] == "span_id"
            assert isinstance(span_id_pair[1], int)
            span_id = span_id_pair[1]

            route_pair = body[2]
            assert isinstance(route_pair, list)
            assert len(route_pair) == 2
            assert route_pair[0] == "route"
            assert isinstance(route_pair[1], int)
            route = route_pair[1]

            contents_pair = body[3]
            assert isinstance(contents_pair, list)
            assert len(contents_pair) == 2
            assert contents_pair[0] == "contents"
            assert isinstance(contents_pair[1], list)

            message = contents_pair[1]
            assert isinstance(message, list)
            assert len(message) == 5
            assert message[0] == "Message"
            message_str_pair = message[4]

            assert isinstance(message_str_pair, list)
            assert len(message_str_pair) == 2
            assert message_str_pair[0] == "str"
            assert isinstance(message_str_pair[1], str)
            message_str = message_str_pair[1]

            return FeedbackMessage(
                doc_id=doc_id,
                span_id=span_id,
                route=route,
                level="Info",
                message=message_str,
            )
        except AssertionError:
            return None


def walk_and_make_symbols_string(sexp: SexpArray) -> SexpArray:
    if isinstance(sexp, list):
        return [walk_and_make_symbols_string(x) for x in sexp]
    if isinstance(sexp, Symbol):
        return str(sexp)
    return sexp
