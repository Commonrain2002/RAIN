Require Import List.
Require Import Nat.
Import ListNotations.
Require Import Lia.
Require Import PeanoNat.

Inductive bin : Type :=
  | Z
  | B0 (n : bin)
  | B1 (n : bin).

Fixpoint incr (m:bin) : bin :=
  match m with
  | Z => B1 Z
  | B0 m' => B1 m'
  | B1 m' => B0 (incr m')
  end.

Fixpoint bin_to_nat (m:bin) : nat :=
  match m with
  | Z => O
  | B0 m' => 2 * (bin_to_nat m')
  | B1 m' => 1 + 2 * (bin_to_nat m')
  end.


(* 

Prove that the following diagram commutes:
                            incr
              bin ----------------------> bin
               |                           |
    bin_to_nat |                           |  bin_to_nat
               |                           |
               v                           v
              nat ----------------------> nat

*)

Theorem bin_to_nat_preserves_incr : forall b : bin,
  bin_to_nat (incr b) = 1 + bin_to_nat b.
Proof.
  intros. induction b as [|b' IHb'|b' IHb']; auto.
  - simpl. rewrite IHb'. lia.
Qed.


Fixpoint nat_to_bin (n:nat) : bin :=
  match n with
  | O => Z
  | S n' => incr (nat_to_bin n')
  end.

Theorem nat_bin_nat : forall n, bin_to_nat (nat_to_bin n) = n.
Proof.
  intros. induction n as [|n' IHn']; auto.
  simpl. rewrite bin_to_nat_preserves_incr. rewrite IHn'. reflexivity.
Qed.

Fixpoint double (n:nat) :=
  match n with
  | O => O
  | S n' => S (S (double n'))
  end.

Lemma double_plus : forall n, double n = n + n .
Proof.
intros n. induction n as [| n' IHn']; auto.
simpl. rewrite IHn'. rewrite plus_n_Sm. reflexivity.
Qed.

Lemma double_incr : forall n : nat, double (S n) = S (S (double n)).
Proof.
  intros. destruct n as [|n'] eqn: N.
  - auto.
  - unfold double. lia.
Qed.

Definition double_bin (b:bin) : bin :=
  match b with
  | Z => Z
  | _ => B0 b
  end.


Lemma double_incr_bin : forall b,
    double_bin (incr b) = incr (incr (double_bin b)).
Proof.
  intros. destruct b as [|b'|b'] eqn: B; auto.
Qed.

(* Define normalize. You will need to keep its definition as simple as possible for later proofs to go smoothly. Do not use bin_to_nat or nat_to_bin, but do use double_bin. *)
(* make sure you use double_bin *)
Fixpoint normalize (b: bin) : bin :=
  match b with
  | Z => Z
  | B0 b' => match b' with
             | Z => Z
             | _ => double_bin (normalize b')
             end
  | B1 b' => incr (double_bin (normalize b'))
  end.


Fixpoint zero_n (n: nat) : bin :=
  match n with
  | O => Z
  | S n' => B0 (zero_n n')
  end.

Fixpoint append_bin (b: bin) (base: bin) : bin :=
  match b with
  | Z => base
  | B0 b' => B0 (append_bin b' base)
  | B1 b' => B1 (append_bin b' base)
  end.

Definition insert_n_zeros_before (b: bin) (n: nat) : bin :=
  append_bin b (zero_n n).

Lemma double_bin_incr: forall b, double_bin (incr b) = incr (incr (double_bin b)).
Proof.
  intros. destruct b as [|b' |b'] eqn: B; simpl; reflexivity.
Qed.

Lemma nat_to_bin_double : forall n:nat, nat_to_bin (double n) = double_bin (nat_to_bin n).
Proof. 
  intros. induction n as [|n' IHn']; auto.
  simpl. rewrite IHn'. rewrite double_bin_incr. reflexivity.
Qed.

Theorem bin_nat_bin : forall b, nat_to_bin (bin_to_nat b) = normalize b.
Proof.
  assert (H: 
    forall b', 
    nat_to_bin (double (bin_to_nat b')) = 
      double_bin (nat_to_bin (bin_to_nat b'))).
    { intros. rewrite nat_to_bin_double. reflexivity. }

  intros. induction b as [|b' IHb' |b' IHb']; simpl; auto.
    - rewrite Nat.add_0_r. rewrite <- double_plus. rewrite H. rewrite IHb'.
      destruct b'; reflexivity.
    - rewrite Nat.add_0_r. rewrite <- double_plus. rewrite H. rewrite IHb'.
    destruct b'; reflexivity.
Qed.