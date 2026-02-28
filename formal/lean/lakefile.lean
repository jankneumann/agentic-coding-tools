import Lake
open Lake DSL

package «parallel-coordination» where
  leanOptions := #[⟨`autoImplicit, false⟩]

@[default_target]
lean_lib ParallelCoordination

lean_lib Proofs where
  roots := #[`Proofs]
