import typing as t
from typing import List, Optional
from src.utils import get_logger
import tiktoken

LOGGER = get_logger("format_prompt")


title_start_delimiter = "["
title_end_delimiter = "]"


def num_gpt4_tokens(string: str) -> int:
    return len(tiktoken.encoding_for_model("gpt-4").encode(string))


def format_message_section(
    header: str,
    content: str,
) -> str:
    return f"""{title_start_delimiter}{header.upper()}{title_end_delimiter}
{content}

"""


def format_message_section_with_budget(
    header: str,
    content_pieces: t.List[str],
    token_budget: int,
) -> str:
    ans = f"{title_start_delimiter}{header.upper()}{title_end_delimiter}\n"
    num_tokens = num_gpt4_tokens(ans)
    if num_tokens > token_budget:
        LOGGER.error(
            "Header too long to fit in token budget",
            extra={"header": header, "token_budget": token_budget},
        )
        raise ValueError("Header too long to fit in token budget")

    content_pieces_copy = content_pieces.copy()
    last_piece_added: t.Optional[str] = None
    while num_tokens < token_budget and len(content_pieces_copy) > 0:
        last_piece_added = content_pieces_copy.pop(0)
        ans += last_piece_added
        num_tokens = num_gpt4_tokens(ans)

    if num_tokens > token_budget and last_piece_added is not None:
        ans = ans[: -len(last_piece_added)]

    return ans


ErrorToken = str
ErrorLineNumber = int
ErrorMessage = str


def format_proposition(
    proposition: str,
) -> str:
    return format_message_section("PROPOSITION", proposition)


def format_current_code(
    current_code: str,
    error: t.Optional[t.Tuple[ErrorToken, ErrorLineNumber, ErrorMessage]],
) -> str:
    if error is None:
        return format_message_section("CURRENT CODE", current_code)
    else:
        return format_message_section(
            "CURRENT CODE",
            code_with_error_span(current_code, error[1], error[0], error[2]),
        )


def format_proof_state(
    proof_state: str,
    error: t.Optional[t.Tuple[ErrorToken, ErrorLineNumber, ErrorMessage]],
) -> str:
    if error is None:
        return format_message_section("PROOF STATE", proof_state)
    else:
        return format_message_section("LAST WORKING PROOF STATE", proof_state)


def format_error(
    error: t.Tuple[ErrorToken, ErrorLineNumber, ErrorMessage],
) -> str:
    return format_message_section(
        "ERROR MESSAGE",
        error[2],
    )


def format_definitions(
    definitions_looked_up: t.List[str],
    tactic_definitions: t.List[str],
    token_budget: int,
) -> str:
    content_pieces = definitions_looked_up + tactic_definitions
    content_pieces = [f"{piece}\n\n" for piece in content_pieces]

    return format_message_section_with_budget(
        "DEFINITIONS",
        content_pieces,
        token_budget,
    )


def format_lemmas(lemmas_looked_up: t.List[str], token_budget: int) -> str:
    content_pieces = lemmas_looked_up
    content_pieces = [f"{piece}\n\n" for piece in content_pieces]
    return format_message_section_with_budget(
        "PROVEN THEOREMS/LEMMAS",
        content_pieces,
        token_budget,
    )


def format_preceding_lines(preceding_lines: str, token_budget: int) -> str:
    split_by_spaces = preceding_lines.split(" ")
    ans = ""
    encoding = tiktoken.encoding_for_model("gpt-4-0613")
    while len(encoding.encode(ans)) < token_budget:
        if len(split_by_spaces) == 0:
            break

        if len(ans) == 0:
            ans = split_by_spaces.pop()
        else:
            ans = split_by_spaces.pop() + " " + ans

    return format_message_section(
        "CODE PRECEDING YOUR PROOF IN THE SAME FILE",
        ans,
    )


def format_user_message(
    proposition: str,
    current_code: str,
    current_proof_state: str,
    lemmas_looked_up: Optional[List[str]],
    definitions_looked_up: Optional[List[str]],
    extra_header: Optional[str],
    extra_content: Optional[str],
) -> str:
    ans = format_proposition(proposition)
    ans += format_current_code(current_code, None)
    ans += format_proof_state(current_proof_state, None)

    if definitions_looked_up is not None:
        ans += format_definitions(definitions_looked_up)
    if lemmas_looked_up is not None:
        ans += format_lemmas(lemmas_looked_up)

    if extra_header is not None and extra_content is not None:
        ans += format_message_section(extra_header, extra_content)

    return ans


def format_error_user_message(
    proposition: str,
    current_code: str,
    error_token: str,
    error_line_number: int,
    error_message: str,
    last_working_proof_state: str,
    lemmas_looked_up: Optional[List[str]],
    definitions_looked_up: Optional[List[str]],
) -> str:
    ans = "The section of code that caused the error is delimited with the <ERROR> and </ERROR> tags.\n These tags are not part of the code, they just indicate where the error is. Make sure you do not include them in any new code you emit.\n\n"

    ans += format_proposition(proposition)

    ans += format_current_code(
        current_code,
        (error_token, error_line_number, error_message),
    )

    ans += format_error(
        (error_token, error_line_number, error_message),
    )
    ans += format_proof_state(
        last_working_proof_state,
        (error_token, error_line_number, error_message),
    )
    if definitions_looked_up is not None:
        ans += format_definitions(
            definitions_looked_up,
        )
    if lemmas_looked_up is not None:
        ans += format_lemmas(
            lemmas_looked_up,
        )

    return ans


def format_global_error_user_message(
    proposition: str,
    current_code: str,
    error_message: str,
) -> str:
    ans = format_proposition(proposition)
    ans += format_current_code(current_code, None)
    ans += format_error(("GLOBAL", 0, error_message))

    return ans


def code_with_error_span(
    code: str, error_line_number: int, error_token: str, error_message: str
) -> str:
    lines = code.strip().split("\n")
    if error_line_number > len(lines) or error_line_number < 1:
        LOGGER.warning(
            f"Line number {error_line_number} out of bounds for code",
            extra={
                "error_line_number": error_line_number,
                "error_token": error_token,
                "code": code,
                "error_message": error_message,
            },
        )
        return code

    line_to_highlight = lines[error_line_number - 1]
    # TODO: what if token appears twice in line?
    error_token_index = line_to_highlight.find(error_token)
    if error_token_index == -1:
        LOGGER.warning(
            f"Token `{error_token}` not found in line {error_line_number} of code",
            extra={
                "error_token": error_token,
                "error_line_number": error_line_number,
                "code": code,
            },
        )
        return code

    line_with_error_span = (
        line_to_highlight[:error_token_index]
        + f"<ERROR> {error_token} </ERROR>"
        + line_to_highlight[error_token_index + len(error_token) :]
    )
    lines[error_line_number - 1] = line_with_error_span
    return "\n".join(lines)
