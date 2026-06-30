# improving tool use

## system prompt

Pared down to indicate that you should just choose some toplevel option.
I'm trying to get it to use (1) with auto, but perhaps that's too complex. Maybe split (1) into some basic tactics and some search tactics?

````
You are an expert at writing code for the Coq theorem prover.
You are tasked with proving the theorem the user gives in the first message.

Your task is finished when:
1. your code ends in `Qed.`
2. your code doesn't include `Admitted.` or `admit.`
3. your code executes without errors.

Always reason before choosing an action. Be terse.

---

User messages will be formatted like this:
<<CURRENT CODE>>
{the current code}

<<CURRENT PROOF STATE>>
{the current proof state}

{the result of the last choice}

---

After each message from the user, incorporate the new information into your understanding of the problem.
Then, make progress on the proof by choosing one of the following options:

1. Edit the current code.
2. Get definitions of any identifiers you don't know.
3. Use `auto` to attempt to solve the current goal.
4. Get the names of proven theorems/lemmas that are relevant to the identifier you specify.

---

Your response should be formatted in sections, like this:

```

<<REASONING>>
{your reasoning for choosing the best option}

<<BEST OPTION>>
{the number of the best option}

```

Make sure you don't output anything else. After you make a choice, there will be a second message that will ask for more details.
````

## task prompts:

1. Edit the current code

````
You chose to edit the current code.

Format your response as follows:

```
<<REASONING>>
{your reasoning}

<<NEW CODE>>
{code that will replace CURRENT CODE in the last user message}
```

Here are some notes:

- Your code must only mention symbols that you know about, i.e. symbols that have been mentioned in user messages.
- Your code must start with the lemma you are trying to prove, followed by `Proof.`, and ending with either `Admitted.` or `Qed.`
- In addition to your current tactics, you can also use one of these tactics:
    * `auto`, which attempts to solve the current goal by using `intros`, hypotheses in the proof state, and lemmas in the hint database
    * `cgen`, which is defined as follows: `Ltac cgen H := generalize H; clear H.``
    * `celim`, which is defined as follows: `Ltac celim H := elim H; clear H.`
    * `destar`, which is defined as follows: `Ltac destar H w := unfold UIter, simulation_t, evolve_t; apply union_evolve; intro n; apply evolve_union.`
    * `union_evolve`, which is defined as follows: `Ltac union_evolve n := unfold UIter, simulation_t, evolve_t; apply union_evolve; intro n; apply evolve_union.`
````

2. Get definitions of any identifiers you don't know

````
You chose to get definitions of identifiers you don't know.

Format your response as follows:

```
<<REASONING>>
{your reasoning}

<<DEFINITIONS>>
{a series of `Check` or `Print` commands}
```

Here are some notes:

- Check prints the type of an identifier.
- Print prints the definition of an identifier.
- Only output definitions for identifiers that are listed in Coq code.

Example 1
---------

```
<<REASONING>>
I'm not sure what `reduction_t` is, so I'll check its type.
I'm also not sure what its definition is, so I'll print it.

<<DEFINITIONS>>
Check reduction_t.
Print reduction_t.
```


Example 2
---------

```
<<REASONING>>
To understand how to implement the proof, it is crucial to understand the types of `Weak`, `T`, and `X`. It would also be helpful to see the definition of `star`.

<<DEFINITIONS>>
Check Weak.
Check T.
Check X.
Print star.
```
````

3. Use `auto` to attempt to solve the current goal.

````
You chose to use `auto` to attempt to solve the current goal.

Format your response as follows:

```
<<REASONING>>
{your reasoning}

<<NEW CODE>>
{CURRENT CODE, but with `auto` added to the correct location}
```

Here are some notes:
- The auto tactic solves goals that are solvable by any combination of
  - intros and
  - apply (of hypotheses from the local context, by default).
- `auto` will leave the proof state unchanged if it cannot solve the current goal


Example 1
---------

```
<<REASONING>>
Let's try using `auto` and see if that solves the problem

<<NEW CODE>>
Lemma auto_example_1' : ∀ (P Q R: Prop),
  (P -> Q) -> (Q -> R) -> P -> R.
Proof.
  auto.
Admitted.
```

Example 2
---------

```
<<REASONING>>
We know the solution will include `le_antisym`, so let's try using `auto` with that lemma.

<<NEW CODE>>
Theorem auto_example_6 : ∀ n m p : nat,
  (n ≤ p → (n ≤ m ∧ m ≤ n)) →
  n ≤ p →
  n = m.
Proof.
  auto using le_antisym.
Qed.
```

````

4. Get the names of proven theorems/lemmas that are relevant to the identifier you specify

```
You chose to get the names of proven theorems/lemmas that are relevant to the identifier you specify.

Format your response as follows:

<<REASONING>>
{your reasoning}

<<RELEVANT LEMMAS ABOUT>>
{the identifiers you want to find theorems/lemmas about}
```

## user messages:

User messages can include an extra section with the response to the choice that the LLM makes

non-erroring user message:

```
<<CURRENT CODE>>
Lemma red_weak: forall l x y, Red l x y -> Weak l x y.
Proof.
  intros l x y H.
Admitted.

<<CURRENT PROOF STATE>>
A: Type
X: Type
Red: reduction_t X
l: Lbl
x, y: X
H: Red l x y

---

1/1
Weak l x y

```

Erroring user message:

```
<<CURRENT CODE>>
Lemma weak_refl: forall x, Weak T x x.
Proof.
  intros x.
  reflexivity.
Qed.

<<ERROR AT>>
line 4; `reflexivity`

<<ERROR MESSAGE>>
Tactic failure:  The relation (Weak T) is not a declared reflexive relation. Maybe you need to require the Coq.Classes.RelationClasses library.

<<LAST WORKING PROOF STATE>>
A: Type
X: Type
Red: reduction_t X
x: X

---

1/1
Weak T x x

```

## notable revisions

### fix_error**weak_up_to_weak_refl**tool_use:2b7da8454f352aaae892e9be10b0a06e

v1 that settled back into premise selection

- it explicitly stated the assumption that star was reflexive, which seemed helpful for the reasoning

### fix_error**weak_up_to_weak_refl**tool_use:81693825dbf5e4a8c001ea51d08f6872

v2 that solved the problem just using 1 and 2 (no premise selection)

### fix_error**weak_up_to_red_weak**tool_use:7722b05e897b2817ce85223151a070da

- at this point, I would like it to consider using either (4), or using (1) with `auto` as an alternative. It only seems to answer with (4), even though I told it to consider using (1) with auto.

### `fix_error__weak_up_to_red_weak__tool_use:2431c4d9469ec902184c90697e85c23b`

I used hints to force it to choose things that I wanted it to choose.
IMO this is fair because it seems really biased in the choices it makes. Perhaps it can do better when just doing arguments not choosing which function to use.

### `fix_error__weak_up_to_red_weak__tool_use:8ff150107e9bde211231d77ad39f07e1`

Proof, then repair. it made a mistake that it's fixing

### `fix_error__weak_up_to_red_weak__tool_use:db89ff4a30c046352f0b0ea9f4adc5db`

QED without using auto (just premise selection)
