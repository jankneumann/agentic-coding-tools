/-
  Parallel Coordination — Abstract model and type definitions.

  Models the core coordination state machine for proving safety
  properties of the parallel-implement-feature workflow.

  Verify with: lake build
-/

-- Agent identity
abbrev AgentId := String

-- Lock key (file path or logical key)
abbrev LockKey := String

-- Task identifier
abbrev TaskId := String

-- Task status
inductive TaskStatus where
  | pending
  | claimed
  | completed
  | failed
  | cancelled
  deriving DecidableEq, Repr

-- Lock state: maps lock keys to optional holders
structure LockState where
  locks : LockKey → Option AgentId

-- Task state
structure TaskState where
  status : TaskStatus
  claimedBy : Option AgentId
  deps : List TaskId

-- Coordination state
structure CoordState where
  lockState : LockKey → Option AgentId
  tasks : TaskId → TaskState
  pausedFeatures : List String

-- Initial state constructor
def CoordState.init (_taskIds : List TaskId) : CoordState :=
  { lockState := fun _ => none
  , tasks := fun _ => { status := .pending, claimedBy := none, deps := [] }
  , pausedFeatures := []
  }

-- Lock acquisition precondition
def canAcquireLock (s : CoordState) (key : LockKey) (agent : AgentId) : Prop :=
  s.lockState key = none ∨ s.lockState key = some agent

-- Task claim precondition
def canClaimTask (s : CoordState) (taskId : TaskId) (_agent : AgentId) : Prop :=
  (s.tasks taskId).status = .pending ∧
  ∀ dep ∈ (s.tasks taskId).deps, (s.tasks dep).status = .completed

-- Task completion precondition
def canCompleteTask (s : CoordState) (taskId : TaskId) (agent : AgentId) : Prop :=
  (s.tasks taskId).status = .claimed ∧
  (s.tasks taskId).claimedBy = some agent
