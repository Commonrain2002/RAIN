# Cobblestone

# Reproduction

For environment setup and runnable reproduction commands, see
[INSTALL.md](./INSTALL.md).

## Prompt Examples

Examples of prompts can be found in [./prompts](./prompts/)

## Evaluation Results

The results of evaluations reported in the paper can be found in [./evaluations](./evaluations/)

## Proofs

Examples of human-written and Cobblestone-generated proofs can be found in [./proofs](./proofs/)

## running evaluations

here are some examples of commands that can be used to run the evaluations. The '--help' flag details all the parameters for the commands

running zero shot:
```
scripts/zero-shot-pass-at-k run -d test -c preceding-lemmas-only

scripts/zero-shot-pass-at-k run -d test -c perfect-premises

scripts/zero-shot-pass-at-k run -d wigderson_test -c preceding-lemmas-only

scripts/zero-shot-pass-at-k run -d wigderson_test -c perfect-premises
```

running cobblestone:
```
scripts/goal-decomposition run -d test_perfect_subgoals -t -c perfect-premises -m 5 -u 09843529ee18492ea2627792635156fa

scripts/goal-decomposition run -d wigderson_test -t -c preceding-lemmas-only -m 5 -u 849eab9ab3d04c89b9aeef60f243d133

scripts/goal-decomposition run -d wigderson_test -c preceding-lemmas-only -m 5 -u 84c25361b1a94adf88cdb5114faa39fc 
```

running TBT search:
```
scripts/next-tactic run -d wigderson_test -c preceding-lemmas-only -m 20 -x 20 -n 5 

scripts/next-tactic run -d test -c preceding-lemmas-only -t -m 20 -x 20 -n 5 
```

# Getting Started

- install poetry
- setup switches

### setup dotenv

```
cp .env.example .env
```

fill in the missing values of the `.env`

### install python prereqs

install python prereqs by running

```
poetry install
```

to enter the virtualenv for this project, run

```
poetry shell
```

Alternatively, if you need to use conda or another package manager, then you can use [requirements.txt](./requirements.txt) instead.

### setup coq

setup 4 switches, each with `coq-serapi` and `coq-hammer`. also, install solvers for hammer. see [make-switch](./scripts/make-switch.bash) for more details.
