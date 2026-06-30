# schema

as of (08/21/2023), the database contains 3 tables:

1. `revision` - aka prompts. These contain json-serialized details of the prompt and other settings for a model.
2. `run` - aka completions. These are model responses to API calls
3. `revision_parent` - which defines a tree relation between chat revisions. If A is a chat sequence, and B is the same chat sequence, but with one extra message, B is a child of a.
