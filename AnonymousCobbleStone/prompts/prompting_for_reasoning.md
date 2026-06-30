# System Message

```
You are an expert at proving theorems in Coq.
You will be given a proposition, definitions, and some potentially useful lemmas in a user message.
Integrating what you learn from the user message, write your reasoning in a section called [REASONING], then write a proof of the proposition using no more than 10 tactics.
You may only use the Coq tactic language. Do not write any vernacular commands like 'Proof.' or 'Qed.'
```

# User Message

```
[PROPOSITION]
forall (l : list A) (a : A) (_ : In a l),
In a (map fst (frequency_list l))

[CURRENT CODE]


[PROOF STATE]
eqA_dec : forall a b : A, sumbool (eq a b) (not (eq a b))
A : Type

---

forall (l : list A) (a : A) (_ : In a l),
In a (map fst (frequency_list l))

[DEFINITIONS]
frequency_list = 
fix frequency_list (l : list A) : list (prod A nat) :=
  match l with
  | nil => nil
  | cons a l1 => add_frequency_list a (frequency_list l1)
  end
     : forall _ : list A, list (prod A nat)

[PROVEN THEOREMS/LEMMAS]

[REASONING]
```