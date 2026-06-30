# Parse-sentence shell contract

ProofAgent does not embed a Coq parser for sentence splitting. It runs a **user-supplied shell command** at the Coq project root and deserializes the combined stdout/stderr as JSON. This document is the full contract for that script.

Implementations are expected to match [CoqStoq](https://github.com/rmatthe1/CoqStoq)-style output (e.g. `vsrocq_split_sentences_CoqStoq path/to/File.v`).

Related code: `CoqSentenceSplitterShell`, `CoqParseSentenceScriptJsonEnvelope`, `CoqSentence`.

---

## Invocation

- **Working directory**: Coq project root (`ProjectFileSystem.ProjectRoot`).
- **Command line**: `{parseSentenceShellLine} {quotedRelativePath}`
  - `parseSentenceShellLine` comes from `--parse-sentence-script` (trimmed; not re-parsed by ProofAgent).
  - `quotedRelativePath` is the target `.v` file relative to the project root, POSIX slashes, shell-quoted (single quotes on Unix, double quotes on Windows).
- **Timeout**: configured per run; on timeout ProofAgent logs and returns an empty sentence list.
- **Success**: process exit code `0`. Combined stdout and stderr must be a **single JSON object** (leading/trailing whitespace allowed).

On non-zero exit, invalid JSON, or missing/empty `sentences`, `CoqSentenceSplitterShell` logs and returns an empty list. Callers treat that as failure to obtain sentences.

---

## Top-level JSON

ProofAgent deserializes only the `sentences` array (`CoqParseSentenceScriptJsonEnvelope`). Other top-level fields may be present and are ignored.

| Field | Required | Notes |
| --- | --- | --- |
| `sentences` | Yes (non-empty for success) | Array of sentence objects (see below). |
| `file` | No | Absolute path; ignored. |
| `position_indexing` | No | e.g. `{"line": "1-based", "column": "0-based"}`; documentation for producers; sentence coordinates must follow this convention. |
| `parse_errors` | No | Ignored by ProofAgent today. |

Example (abbreviated from real tool output):

```json
{
  "file": "/abs/path/to/A.v",
  "position_indexing": {"line": "1-based", "column": "0-based"},
  "sentences": [
    {
      "index": 0,
      "byte_start": 0,
      "byte_end": 24,
      "start_line": 1,
      "start_column": 0,
      "end_line": 1,
      "end_column": 24,
      "classification": "VtSideff([test11],VtLater)",
      "vernac_type": "definition",
      "name": "test11",
      "tokens": ["Definition", "test11", ":=", "42", "."],
      "text": "Definition test11 := 42."
    },
    {
      "index": 1,
      "byte_start": 27,
      "byte_end": 72,
      "start_line": 4,
      "start_column": 0,
      "end_line": 4,
      "end_column": 45,
      "classification": "VtStartProof(GuaranteesOpacity,[test])",
      "text": "Lemma test : forall x y : nat, x + y = y + x."
    },
    {
      "index": 2,
      "byte_start": 73,
      "byte_end": 79,
      "start_line": 5,
      "start_column": 0,
      "end_line": 5,
      "end_column": 6,
      "classification": "VtProofStep(bullet)",
      "text": "Proof."
    },
    {
      "index": 3,
      "byte_start": 80,
      "byte_end": 89,
      "start_line": 6,
      "start_column": 0,
      "end_line": 6,
      "end_column": 9,
      "classification": "VtQed(VtKeep(VtKeepAxiom))",
      "text": "Admitted."
    }
  ],
  "parse_errors": []
}
```

---

## Sentence object (`CoqSentence`)

JSON property names map to `CoqSentence` fields:

| JSON property | C# property | Semantics |
| --- | --- | --- |
| `index` | `Index` | Stable sentence order in the file. |
| `start_line` | `StartLineOneBased` | 1-based line. |
| `start_column` | `StartColumnZeroBased` | 0-based column. |
| `end_line` | `EndLineOneBased` | 1-based line. |
| `end_column` | `EndColumnZeroBased` | 0-based column (exclusive end in CoqStoq style). |
| `text` | `Text` | Source text of the sentence. |
| `vernac_type` | `VernacType` | Splitter tag; parsed at ingest to `CoqSentenceVernacType` (see below). |
| `name` | `Name` | Primary identifier for the sentence when applicable (empty string if none). |
| `tokens` | `Tokens` | Token sequence for the sentence (may be empty). |
| `classification` | `Classification` | CoqStoq tag string; parsed at ingest to `CoqSentenceClassification` (see below). |

Extra per-sentence fields (e.g. `byte_start`, `byte_end`) may be present and are ignored.

---

## `vernac_type` tags and in-engine enum

Scripts emit `vernac_type` strings (e.g. `definition`, `notation`, `theorem`, `other`). On ingest (`CoqSentenceVernacTypeJsonConverter`), each string maps to `CoqSentenceVernacType` (trimmed, case-insensitive exact match):

| Script `vernac_type` | `CoqSentenceVernacType` |
| --- | --- |
| `definition` | `Definition` |
| `fixpoint` | `Fixpoint` |
| `inductive` | `Inductive` |
| `theorem` | `Theorem` |
| `require` | `Require` |
| Anything else (including `notation`, `other`, empty) | `Other` |

---

## `classification` tags and in-engine enum

Scripts should emit full CoqStoq `classification` strings. On ingest (JSON deserialization via `CoqSentenceClassificationJsonConverter`), each string maps to `CoqSentenceClassification` (prefix match, longest first):

| CoqStoq prefix (after trim) | `CoqSentenceClassification` |
| --- | --- |
| `VtProofStep(bullet)` | `Bullet` |
| `VtProofStep(curly)` | `Curly` |
| `VtProofStep` | `Step` |
| Anything else (including `VtSideff(...)`, `VtStartProof(...)`, `VtQed(...)`, empty) | `Others` |

All sentences need plausible spans (`index`, lines, columns, `text`). **Bullet and multi-error logic** uses the enum:

- **Proof-step region** (`Step`, `Bullet`, `Curly`): from the error anchor forward, `CoqBulletAnalyzer` accepts only these while scanning for the bullet end. Closing sentences must parse as `Others` (e.g. `VtQed(...)` on `Admitted.` / `Qed.`).
- **Bullet stack** (`Bullet`, `Curly`): `CoqBulletStack` and `CoqSentenceAnalyzer.CheckIsBulletOrCurly` react only to these; plain `Step` does not change the stack.
- **`Others`**: positioning only; no proof-step or bullet-stack semantics.

The original CoqStoq parameter lists (e.g. inside `VtSideff(...)`) are not stored after parsing.

---

## Consumers

| Component | Uses sentences for |
| --- | --- |
| `ICoqSentenceAnalyzer` / `CoqSentenceAnalyzer` | Map line/column to a sentence; bullet/curly check via classification. |
| `CoqBulletAnalyzer` | Bullet stack and bullet-end region from classifications + text. |
| `CoqProofBulletIterationPlanner` | Iteration planning over sentence indices. |
| `CoqEnvironmentCapturer` | Insertion offsets at sentence boundaries. |
