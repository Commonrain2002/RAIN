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
We are given a list 'l' of elements of type A and an element 'a' of type A that is known to be in 'l'. We need to prove that 'a' is in the list of the first elements of the pairs formed by 'frequency_list'. This can be achieved by reasoning in the following manner:

1. 'frequency_list' calculates the frequencies of the elements in a list, so if we have any 'a' in 'l', it should appears in the pairs made by 'frequency_list'. 

2. The first element of the pairs in the list created by 'frequency_list' is the actual element from the list and second element signifies the frequency or count of that element in 'l'.

3. Since 'a' is present in 'l', its frequency would at least be 1 and hence a pair with 'a' as the first element would be formed.

4. Hence, in the list created by using the map with 'fst' on the 'frequency_list', 'a' would be present. Therefore, we can conclude that for all elements 'a' in 'l', 'a' is also in 'map fst (frequency_list l)'.

To prove this in Coq, we need to do induction on 'l'. In the base case, 'l' is empty, so 'a' can't be in 'l' which contradicts our assumption and hence is not valid. For the inductive case, we divide 'l' into 'a' and 'l1'. For any 'a' in 'l', if it's same as 'a' being considered currently, we show that it appears in the frequency list by using Coq's reflexivity tactic. If it's in rest of the list 'l1', we use the inductive hypothesis to show that it appears in 'lambda x => map fst (frequency_list x)'. Using element 'a' and 'cons' on 'l1', we argue that 'a' will be included in 'lambda x => map fst (frequency_list x)' for 'cons a l1'. This concludes the proof for the inductive case and hence, our overall proposition holds.

```