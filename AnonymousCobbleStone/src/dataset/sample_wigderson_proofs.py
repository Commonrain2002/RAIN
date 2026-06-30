from pathlib import Path
import typing as t
import re
from pprint import pprint
import coq_serapy as c
import json
import pickle
import random

from src.config import CONFIG
from src.coq_serapy_util import (
    LemmaLocation,
    read_commands,
    get_section_name_from_command,
)
from src.dataset import Example


section_regex = re.compile(r"Section\s+(\w+)")
end_section_regex = re.compile(r"End\s+(\w+)")
lemma_regex = re.compile(
    r"(Example|Lemma|Theorem|Function)\s+(\w+)[\s\S]*(?!:=):([\s\S]*)\."
)
# lemma_regex = re.compile(r"(Example|Lemma|Theorem)\s+(\w+)\s*(\{\w+\})?\s*(\(.*\))?\s*:([\s\S]*)\.")


def get_all_lemma_locations(file: Path) -> t.List[Example]:
    commands = read_commands(file.read_text())

    print(file)

    section_names: t.List[str] = []
    lemmas: t.List[Example] = []
    in_proof = False
    for command, _ in commands:
        command = c.coq_util.kill_comments(command).strip()
        section_match = section_regex.match(command)
        if section_match is not None:
            section_name = section_match.group(1)
            section_names.append(section_name)
            continue

        end_section_match = end_section_regex.match(command)
        if end_section_match is not None:
            section_name = end_section_match.group(1)
            if section_name != section_names[-1]:
                raise ValueError(
                    f"Section name mismatch: {section_name} != {section_names[-1]}"
                )
            section_names.pop()
            continue

        lemma_match = lemma_regex.match(command)
        if lemma_match is not None:
            print(command)
            lemma_name = lemma_match.group(2)
            lemma_location = LemmaLocation(
                project_name="coq-wigderson",
                file_name=file.name,
                lemma_name=lemma_name,
                section_names=section_names.copy(),
                coq_version="8.13",
            )
            example = Example(
                gold_standard_proof="",
                proposition_command=command,
                location=lemma_location,
            )
            lemmas.append(example)

        if command == "Proof.":
            in_proof = True

        if in_proof and (command == "Admitted." or command == "Abort."):
            print("admitted or abort.")
            # remove the last lemma location
            lemmas.pop()

        if (
            command == "Qed."
            or command == "Defined."
            or command == "Admitted."
            or command == "Abort."
        ):
            in_proof = False
    return lemmas


WIGDERSON_DIR = Path(CONFIG.ROOT_DIR) / "coq-projects/coq-wigderson"
COQ_PROJECT_PATH = WIGDERSON_DIR / "_CoqProject"


def get_all_wigderson_lemmas():
    # filenames = all files after the first
    filenames = [
        line.strip() for line in COQ_PROJECT_PATH.read_text().split("\n")[1:] if line
    ]
    file_paths = [WIGDERSON_DIR / filename for filename in filenames]
    lemmas: t.Dict[Path, t.List[Example]] = {
        file: get_all_lemma_locations(file) for file in file_paths
    }

    return lemmas


def sample_wigderson_lemmas(
    n: int, exclude_dataset: t.List[Example]
) -> t.List[Example]:
    lemmas = get_all_wigderson_lemmas()

    lemmas_not_in_dataset: dict[Path, t.List[Example]] = {
        file: [lemma for lemma in lemmas if lemma not in exclude_dataset]
        for file, lemmas in lemmas.items()
    }
    concatenated_lemmas = [
        lemma for file, lemmas in lemmas_not_in_dataset.items() for lemma in lemmas
    ]

    return sorted(random.sample(concatenated_lemmas, n), key=lambda x: x.name)
