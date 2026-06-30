# System Message

```
You are an expert at proving theorems in Coq.
You will be given a proof context, definitions, and some potentially useful lemmas in a user message.
Your task is to write down the next tactic in a correct proof of the proposition.

Integrating what you learn from the user message, write down the next tactic.

You may only use the Coq tactic language. Do not write any vernacular commands like 'Proof.' or 'Qed.'
Write only one tactic.
```

# User Message

```
[PROPOSITION]
forall (f : forall _ : positive, bool) (l : list positive)
  (_ : Sorted E.lt l), Sorted E.lt (filter f l)

[CURRENT CODE]


[PROOF STATE]

---

forall (f : forall _ : positive, bool) (l : list positive)
  (_ : Sorted E.lt l), Sorted E.lt (filter f l)

[DEFINITIONS]
E.lt = E.bits_lt
     : forall (_ : positive) (_ : positive), Prop

[PROVEN THEOREMS/LEMMAS]
Example InA_example: InA same_mod_10 27 [3;17;2].

Example domain_example_map: S.elements (Mdomain example_map) = [2;9;3]%positive.

Example equivlistA_example: equivlistA same_mod_10 [3; 17] [7; 3; 27].

Goal E.eq = @eq positive.

Goal E.t = positive.

Lemma SortE_equivlistE_eqlistE: forall al bl, Sorted E.lt al -> Sorted E.lt bl -> equivlistA E.eq al bl -> eqlistA E.eq al bl.

Lemma eqlistA_Eeq_eq: forall al bl, eqlistA E.eq al bl <-> al=bl.

Lemma lt_proper: Proper (eq ==> eq ==> iff) E.lt.

Lemma lt_strict: StrictOrder E.lt.

[REASONING]
The goal here is prove that a filtered list will remain sorted if the original list was sorted. The sorting is defined under the relation `E.lt` (`E.bits_lt`). Unfortunately, there are no provided lemmas or theorems that directly relate to the `filter` function from Coq's `List` module, nor any that provide an indirect link between sortedness and filtering.

However, I might attempt an inductive approach by destructuring the list `l`. If `l` is empty, the filtered list is also empty which trivially satisfies the `Sorted` property. If `l` consists of a head and a tail, one would have to reason about what happens after performing the filter operation, requiring to make use of `f` too. For this reason, it might be beneficial to perform a case analysis on `l` to see what the goal will decompose into.
```