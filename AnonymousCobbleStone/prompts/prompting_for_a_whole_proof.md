# System Message

```
You are an expert at proving theorems in Coq.
You will be given a proposition, definitions, and some potentially useful lemmas in a user message.
Integrating what you learn from the user message, write a proof of the proposition using no more than 10 tactics.
You may only use the Coq tactic language. Do not write any vernacular commands like 'Proof.' or 'Qed.
```

# User Message

```
[PROPOSITION]
forall (a b : Term) (_ : zeroP a), zeroP (multTerm a b)

[CURRENT CODE]


[PROOF STATE]
os : OrderStructure (mon n) (zero_mon n) ltM (mult_mon n)
ltM_dec : forall a b : mon n, sumor (sumbool (ltM a b) (ltM b a)) (eq a b)
ltM : forall (_ : mon n) (_ : mon n), Prop
n : nat
eqA_dec : forall a b : A, sumbool (eqA a b) (not (eqA a b))
cs : CoefStructure A A0 A1 eqA plusA invA minusA multA divA
divA : forall (_ : A) (b : A) (_ : not (eqA b A0)), A
minusA,multA : forall (_ : A) (_ : A), A
invA : forall _ : A, A
plusA : forall (_ : A) (_ : A), A
eqA : forall (_ : A) (_ : A), Prop
A0,A1 : A
A : Set

---

forall (a b : Term) (_ : zeroP a), zeroP (multTerm a b)

[DEFINITIONS]
Record CoefStructure (A : Set) (A0 A1 : A)
(eqA : forall (_ : A) (_ : A), Prop) (plusA : forall (_ : A) (_ : A), A)
(invA : forall _ : A, A) (minusA multA : forall (_ : A) (_ : A), A)
(divA : forall (_ : A) (b : A) (_ : not (eqA b A0)), A) : Prop
  := mkCoefStructure
  { A1_diff_A0 : not (eqA A1 A0);
    eqA_ref : reflexive A eqA;
    eqA_sym : symmetric A eqA;
    eqA_trans : transitive A eqA;
    plusA_assoc : forall a b c : A,
                  eqA (plusA a (plusA b c)) (plusA (plusA a b) c);
    plusA_com : forall a b : A, eqA (plusA a b) (plusA b a);
    plusA_eqA_comp : forall (a b c d : A) (_ : eqA a c) (_ : eqA b d),
                     eqA (plusA a b) (plusA c d);
    plusA_A0 : forall a : A, eqA a (plusA a A0);
    invA_plusA : forall a : A, eqA A0 (plusA a (invA a));
    invA_eqA_comp : forall (a b : A) (_ : eqA a b), eqA (invA a) (invA b);
    minusA_def : forall a b : A, eqA (minusA a b) (plusA a (invA b));
    multA_eqA_comp : forall (a b c d : A) (_ : eqA a c) (_ : eqA b d),
                     eqA (multA a b) (multA c d);
    multA_assoc : forall a b c : A,
                  eqA (multA a (multA b c)) (multA (multA a b) c);
    multA_com : forall a b : A, eqA (multA a b) (multA b a);
    multA_dist_l : forall a b c : A,
                   eqA (plusA (multA c a) (multA c b)) (multA c (plusA a b));
    multA_A0_l : forall a : A, eqA (multA A0 a) A0;
    multA_A1_l : forall a : A, eqA (multA A1 a) a;
    divA_rew : forall (a b : A) (nZ1 nZ2 : not (eqA b A0)),
               eq (divA a b nZ1) (divA a b nZ2);
    divA_is_multA : forall (a b : A) (nZb : not (eqA b A0)),
                    eqA a (multA (divA a b nZb) b);
    divA_eqA_comp : forall (a b c d : A) (nZb : not (eqA b A0))
                      (nZd : not (eqA d A0)) (_ : eqA a c) 
                      (_ : eqA b d), eqA (divA a b nZb) (divA c d nZd);
    divA_multA_comp_r : forall (a b c : A) (nZc : not (eqA c A0)),
                        eqA (divA (multA a b) c nZc) (multA (divA a c nZc) b);
    divA_invA_r : forall (a b : A) (nZb : not (eqA b A0))
                    (nZib : not (eqA (invA b) A0)),
                  eqA (divA a (invA b) nZib) (invA (divA a b nZb)) }

                     function_scope function_scope function_scope
                       function_scope function_scope function_scope
                       function_scope function_scope _ _ _ _ function_scope
                       function_scope function_scope function_scope
                       function_scope function_scope function_scope
                       function_scope function_scope function_scope
                       function_scope function_scope function_scope
                       function_scope function_scope function_scope

Record OrderStructure (A : Set) (M1 : A) (ltM : forall (_ : A) (_ : A), Prop)
(plusM : forall (_ : A) (_ : A), A) : Prop := mkOrderStructure
  { M1_min : forall x : A, not (ltM x M1);
    ltM_nonrefl : forall x : A, not (ltM x x);
    ltM_trans : transitive A ltM;
    ltM_wf : well_founded ltM;
    ltM_plusr : forall (x y z : A) (_ : ltM x y), ltM (plusM x z) (plusM y z);
    ltM_plusl : forall (x y z : A) (_ : ltM x y), ltM (plusM z x) (plusM z y) }

                        function_scope function_scope function_scope _ _

*** [ltM_dec : forall a b : mon n,
               sumor (sumbool (ltM a b) (ltM b a)) (eq a b)]

Inductive mon : forall _ : nat, Set :=
    n_0 : mon O | c_n : forall (d _ : nat) (_ : mon d), mon (S d)

multTerm = 
fun H' : Term =>
let (b2, c2) := H' in
fun H1' : Term =>
let (b3, c3) := H1' in pair (multA b2 b3) (mult_mon n c2 c3)
     : forall (_ : Term) (_ : Term), Term

mult_mon = 
fun d : nat =>
nat_rec (fun d0 : nat => forall (_ : mon d0) (_ : mon d0), mon d0)
  (fun _ _ : mon O => n_0)
  (fun (n : nat) (Rec : forall (_ : mon n) (_ : mon n), mon n)
     (S1 S2 : mon (S n)) =>
   c_n n (Nat.add (pmon1 (S n) S1) (pmon1 (S n) S2))
     (Rec (pmon2 (S n) S1) (pmon2 (S n) S2))) d
     : forall (d : nat) (_ : mon d) (_ : mon d), mon d

zeroP = 
fun H' : Term => let (a, _) := H' in eqA a A0
     : forall _ : Term, Prop

zero_mon = 
fun d : nat =>
nat_rec (fun d0 : nat => mon d0) n_0
  (fun (n : nat) (Rec : mon n) => c_n n O Rec) d
     : forall d : nat, mon d

[PROVEN THEOREMS/LEMMAS]
eqA_trans : forall (A : Set) (A0 A1 : A) (eqA : forall (_ : A) (_ : A), Prop) (plusA : forall (_ : A) (_ : A), A) (invA : forall _ : A, A) (minusA multA : forall (_ : A) (_ : A), A) (divA : forall (_ : A) (b : A) (_ : not (eqA b A0)), A) (_ : CoefStructure A A0 A1 eqA plusA invA minusA multA divA), transitive A eqA

```
