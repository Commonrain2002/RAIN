# *** PREAMBLE ***
# ================


# based on https://tech.davis-hansson.com/p/make

# use bash as the shell, as sh could be bound to a variety of shells
SHELL := bash
# run all recipes in a single shell
.ONESHELL:

# based on http://redsymbol.net/articles/unofficial-bash-strict-mode/
# flags for more sane shell scripts and clearer errors
.SHELLFLAGS := -eu -o pipefail -c

# delete target if recipe fails
# .DELETE_ON_ERROR:

MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

# use '>' instead of '\t' to denote a recipe
ifeq ($(origin .RECIPEPREFIX), undefined)
  $(error This Make does not support .RECIPEPREFIX. Please use GNU Make 4.0 or later)
endif
.RECIPEPREFIX = >


# *** TARGETS ***
# ===============

switches: coq-8.10 coq-8.11 coq-8.12
> 

coq-%: .sentinels/coq-%
> 

.PRECIOUS: .sentinels/coq-%
.sentinels/coq-%:
> scripts/make-switch.bash $*
> touch $@



coqgym:
> cd coq-projects/coqgym/coq-projects && $(MAKE)

format:
> black src

migrate:
> ./scripts/migrate.bash

new-migration:
> ./scripts/new-migration.bash

print:
> ./scripts/print.bash

list-names:
> ./scripts/list-names.bash

chat-tree:
> ./scripts/chat-tree.bash

auto-chat-tree:
> ./scripts/automated-chat-tree.bash

automated-chat-tree:
> ./scripts/automated-chat-tree.bash

test/coq-serapy:
> python src/test_coq_serapy.py

test/coq-serapy-util:
> python src/coq_serapy_util.test.py

test/environment:
> python src/environment.test.py

test/parse-llm-response:
> python src/parse_llm_response.test.py

test/prompt:
> python src/prompt.test.py

db.sqlite3: migrate populate/import-fs-revisions populate/add-types-to-revisions

update-coq-serapy:
> poetry update coq-serapy

.PHONY: switches format \
test/coq-serapy test/environment test/parse_llm_response \
test/coq_serapy_util test/prompt\
update-coq-serapy \
chat-tree auto-chat-tree automated-chat-tree \
list-targets $(TARGETS) \
migrate new-migration print list-names \
populate/import-fs-revisions populate/add-types-to-revisions
