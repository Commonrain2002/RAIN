# TODO

## next actions

- [ ] plug it into a larger codebase like weak up to
- [ ] improve the way we display the state (allow for >1 goal)
- [ ] write an env test that uses lia to solve a goal

- [ ] prompt the user for a name for each rollout

- [ ] consider making it possible to allow the model to edit imports
- [ ] delete earlier history when we fill up a contexxt window

## finished

- [x] add imports to environment to support lia
- [x] fix issues mentioned in this PR:
  - https://github.com/HazardousPeach/coq_serapy/pull/7
- [x] revert formatting changes in coq_serapy
- [x] add import for lia
- [x] fix errors with print and check
- [x] fix search. it should only surface lemma definitions, and should be comprehensive
- [x] add error line number to the error message
- [x] do a successful rollout on one_plus_n
- [x] parse actions from LLM results
- [x] add a "search" for relevant lemmas action (could just use the search vernac)
- [x] add a "definitions" action
- [x] define a simple action space with just and edit action. modify the environment to add a next(action) method that returns an observation and whether the episode is done
- [x] add a `done` property
- [x] create an observe() function that can give you a correctly formatted user response about the state of the environment
  - right now, we're manually rerunning each proof from the start. that's ok
- [x] break (1) into 2 toplevel actions, with restricted tactic options for each (one w/ simple tactics, one with search tactics like auto)
  - try this with `fix_error__weak_up_to_red_weak__tool_use`, which explicitly requires some premise selection
- [x] add examples with mixed Print and Check to (2)
- [x] remove option 3 (view proof state)
  - option 3 can be thought of as "choosing to backtrack"
  - a better choice might be to (1) give it the option to give up, and (2) add "delete code" as an option
- [x] split solving the problem into (1) picking an action, and (2) picking "how" to do that action.
- [x] add coq-serapy's dependencies (ocaml and python) to docker
- [x] install coq-serapy (https://github.com/HazardousPeach/coq_serapy)
- [x] change project name in README.md
- [x] change project name in devcontainer.json
- [x] create readme and todo
- [x] setup automatic history

## someday/maybe

- [ ] improve performance of executing between edits to code
- [ ] refine auto prompt to use examples, rather than documentation
- [ ] try just using "auto" at every point where it's possible
  - that's a lot of places. just add a toplevel task asking the llm to say where to try auto
  - or append auto onto the end of the code and disallow any admits
- [ ] add an option to suggest a lemma and get it proven (I'll prove it on the side.)
- [ ] refine the system prompt to explicitly state its assumptions and the goal state that it's trying to reach
- [ ] a tree viz w/ just the choice numbers
- [ ] if I make the current path deep enough, it's slowing down. doesn't appear to be a memory leak, as closing and opening doesn't fix

## ideas

### useful coq_serapy files

https://github.dev/UCSD-PL/proverbot9001/blob/b9f3034549c2e24d7637f358b857f0ecfffa0436/src/search_strategies.py#L331
https://github.com/sakekasi/coq_serapy/blob/2207e4d90f60b288b2791fd756ccb894c4b8a901/src/coq_serapy/coq_agent.py#L71
https://github.com/sakekasi/coq_serapy/blob/2207e4d90f60b288b2791fd756ccb894c4b8a901/src/coq_serapy/coq_util.py#L527

### other

- too many "consider x"'s might be a smell that the high level actions ought to be further broken up
- give me a list of all the tactics you think could be possible with docs (inversion of me telling it)
- more structured reasoning. nl reasoning, tactics you might think are useful and why, etc.
- knowing "when to use auto" is too hard. force it to always try auto before trying something else, like proverbot does.
- editing can be broken down into (1) generating the whole proof or (2) fixing the proof based on errors
