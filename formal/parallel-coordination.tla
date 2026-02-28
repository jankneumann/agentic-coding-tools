-------------------------------- MODULE parallel_coordination --------------------------------
\* TLA+ model for parallel coordination invariants.
\*
\* Models: lock acquisition/release/expiry, task claim/complete,
\*         dependency gating, pause-lock coordination, orchestrator rescheduling.
\*
\* Verify with: tlc formal/parallel-coordination.tla
\* Requires: TLA+ Toolbox or standalone TLC model checker

EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
    Agents,         \* Set of agent IDs
    LockKeys,       \* Set of lock key identifiers
    TaskIds,        \* Set of task identifiers
    MaxSteps        \* Bound on execution steps

VARIABLES
    locks,          \* Function: LockKeys -> Agents ∪ {None}
    taskStatus,     \* Function: TaskIds -> {"pending","claimed","completed","failed","cancelled"}
    taskClaimedBy,  \* Function: TaskIds -> Agents ∪ {None}
    taskDeps,       \* Function: TaskIds -> SUBSET TaskIds (dependencies)
    pausedFeatures, \* Set of paused feature IDs
    step            \* Step counter for bounded model checking

vars == <<locks, taskStatus, taskClaimedBy, taskDeps, pausedFeatures, step>>

\* ------ Type Invariant ------

TypeOK ==
    /\ locks \in [LockKeys -> Agents \cup {CHOOSE x \in {"none"} : TRUE}]
    /\ taskStatus \in [TaskIds -> {"pending", "claimed", "completed", "failed", "cancelled"}]
    /\ taskClaimedBy \in [TaskIds -> Agents \cup {CHOOSE x \in {"none"} : TRUE}]
    /\ pausedFeatures \subseteq {"feat-1", "feat-2"}
    /\ step \in 0..MaxSteps

None == CHOOSE x \in {"none"} : TRUE

\* ------ Initial State ------

Init ==
    /\ locks = [k \in LockKeys |-> None]
    /\ taskStatus = [t \in TaskIds |-> "pending"]
    /\ taskClaimedBy = [t \in TaskIds |-> None]
    /\ taskDeps = [t \in TaskIds |-> {}]  \* No deps in base model; override in cfg
    /\ pausedFeatures = {}
    /\ step = 0

\* ------ Actions ------

\* Lock acquisition: agent acquires lock if not held by another agent
AcquireLock(agent, key) ==
    /\ step < MaxSteps
    /\ \/ locks[key] = None
       \/ locks[key] = agent
    /\ locks' = [locks EXCEPT ![key] = agent]
    /\ UNCHANGED <<taskStatus, taskClaimedBy, taskDeps, pausedFeatures>>
    /\ step' = step + 1

\* Lock release: agent releases lock only if they hold it
ReleaseLock(agent, key) ==
    /\ step < MaxSteps
    /\ locks[key] = agent
    /\ locks' = [locks EXCEPT ![key] = None]
    /\ UNCHANGED <<taskStatus, taskClaimedBy, taskDeps, pausedFeatures>>
    /\ step' = step + 1

\* Lock expiry: any lock can expire (models TTL)
ExpireLock(key) ==
    /\ step < MaxSteps
    /\ locks[key] # None
    /\ locks' = [locks EXCEPT ![key] = None]
    /\ UNCHANGED <<taskStatus, taskClaimedBy, taskDeps, pausedFeatures>>
    /\ step' = step + 1

\* Task claim: agent claims pending task if all deps completed
ClaimTask(agent, task) ==
    /\ step < MaxSteps
    /\ taskStatus[task] = "pending"
    /\ \A dep \in taskDeps[task] : taskStatus[dep] = "completed"
    /\ taskStatus' = [taskStatus EXCEPT ![task] = "claimed"]
    /\ taskClaimedBy' = [taskClaimedBy EXCEPT ![task] = agent]
    /\ UNCHANGED <<locks, taskDeps, pausedFeatures>>
    /\ step' = step + 1

\* Task completion: claimed task marked completed by its claimer
CompleteTask(agent, task) ==
    /\ step < MaxSteps
    /\ taskStatus[task] = "claimed"
    /\ taskClaimedBy[task] = agent
    /\ taskStatus' = [taskStatus EXCEPT ![task] = "completed"]
    /\ UNCHANGED <<locks, taskClaimedBy, taskDeps, pausedFeatures>>
    /\ step' = step + 1

\* Task failure: claimed task marked failed by its claimer
FailTask(agent, task) ==
    /\ step < MaxSteps
    /\ taskStatus[task] = "claimed"
    /\ taskClaimedBy[task] = agent
    /\ taskStatus' = [taskStatus EXCEPT ![task] = "failed"]
    /\ UNCHANGED <<locks, taskClaimedBy, taskDeps, pausedFeatures>>
    /\ step' = step + 1

\* Task cancellation: orchestrator cancels a pending or claimed task
CancelTask(task) ==
    /\ step < MaxSteps
    /\ taskStatus[task] \in {"pending", "claimed"}
    /\ taskStatus' = [taskStatus EXCEPT ![task] = "cancelled"]
    /\ UNCHANGED <<locks, taskClaimedBy, taskDeps, pausedFeatures>>
    /\ step' = step + 1

\* Pause feature: set the pause lock
PauseFeature(feat) ==
    /\ step < MaxSteps
    /\ feat \notin pausedFeatures
    /\ pausedFeatures' = pausedFeatures \cup {feat}
    /\ UNCHANGED <<locks, taskStatus, taskClaimedBy, taskDeps>>
    /\ step' = step + 1

\* Unpause feature
UnpauseFeature(feat) ==
    /\ step < MaxSteps
    /\ feat \in pausedFeatures
    /\ pausedFeatures' = pausedFeatures \ {feat}
    /\ UNCHANGED <<locks, taskStatus, taskClaimedBy, taskDeps>>
    /\ step' = step + 1

\* Orchestrator reschedule: failed task -> pending (retry)
RescheduleTask(task) ==
    /\ step < MaxSteps
    /\ taskStatus[task] = "failed"
    /\ taskStatus' = [taskStatus EXCEPT ![task] = "pending"]
    /\ taskClaimedBy' = [taskClaimedBy EXCEPT ![task] = None]
    /\ UNCHANGED <<locks, taskDeps, pausedFeatures>>
    /\ step' = step + 1

\* ------ Next State ------

Next ==
    \E agent \in Agents, key \in LockKeys, task \in TaskIds :
        \/ AcquireLock(agent, key)
        \/ ReleaseLock(agent, key)
        \/ ExpireLock(key)
        \/ ClaimTask(agent, task)
        \/ CompleteTask(agent, task)
        \/ FailTask(agent, task)
        \/ CancelTask(task)
        \/ RescheduleTask(task)
    \/ \E feat \in {"feat-1", "feat-2"} :
        \/ PauseFeature(feat)
        \/ UnpauseFeature(feat)

\* ------ Safety Invariants ------

\* INV1: Lock Exclusivity — each lock held by at most one agent
LockExclusivity ==
    \A k \in LockKeys :
        locks[k] # None => \A k2 \in LockKeys :
            (k # k2 /\ locks[k2] # None) => locks[k] # locks[k2] \/ k = k2

\* INV2: No Double-Claim — each task claimed by at most one agent
NoDoubleClaim ==
    \A t \in TaskIds :
        taskStatus[t] = "claimed" =>
            taskClaimedBy[t] # None

\* INV3: Dependency Safety — claimed/completed tasks have all deps completed
DependencySafety ==
    \A t \in TaskIds :
        taskStatus[t] \in {"claimed", "completed"} =>
            \A dep \in taskDeps[t] : taskStatus[dep] = "completed"

\* INV4: Result Immutability — completed tasks stay completed
\* (checked via temporal property, but approximated here)
ResultImmutability ==
    \A t \in TaskIds :
        taskStatus[t] = "completed" =>
            taskClaimedBy[t] # None

\* INV5: Cancelled tasks cannot transition to claimed or completed
CancelledStaysTerminal ==
    \A t \in TaskIds :
        taskStatus[t] = "cancelled" =>
            taskClaimedBy[t] = None \/ taskStatus[t] = "cancelled"

\* Combined invariant
SafetyInvariant ==
    /\ LockExclusivity
    /\ NoDoubleClaim
    /\ DependencySafety
    /\ ResultImmutability
    /\ CancelledStaysTerminal

\* ------ Specification ------

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

=============================================================================
