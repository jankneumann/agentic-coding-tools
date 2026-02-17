----------------------------- MODULE coordination -----------------------------
EXTENDS Naturals, Sequences, TLC

CONSTANT Agents, Files, Tasks

VARIABLES locks, taskOwner, taskStatus

Init ==
    /\ locks = [f \in Files |-> NULL]
    /\ taskOwner = [t \in Tasks |-> NULL]
    /\ taskStatus = [t \in Tasks |-> "pending"]

AcquireLock(a, f) ==
    /\ locks[f] = NULL
    /\ locks' = [locks EXCEPT ![f] = a]
    /\ UNCHANGED <<taskOwner, taskStatus>>

ReleaseLock(a, f) ==
    /\ locks[f] = a
    /\ locks' = [locks EXCEPT ![f] = NULL]
    /\ UNCHANGED <<taskOwner, taskStatus>>

ClaimTask(a, t) ==
    /\ taskStatus[t] = "pending"
    /\ taskOwner[t] = NULL
    /\ taskOwner' = [taskOwner EXCEPT ![t] = a]
    /\ taskStatus' = [taskStatus EXCEPT ![t] = "claimed"]
    /\ UNCHANGED locks

CompleteTask(a, t) ==
    /\ taskStatus[t] = "claimed"
    /\ taskOwner[t] = a
    /\ taskStatus' = [taskStatus EXCEPT ![t] = "completed"]
    /\ UNCHANGED <<locks, taskOwner>>

ExpireClaim(t) ==
    /\ taskStatus[t] = "claimed"
    /\ taskOwner' = [taskOwner EXCEPT ![t] = NULL]
    /\ taskStatus' = [taskStatus EXCEPT ![t] = "pending"]
    /\ UNCHANGED locks

Next ==
    \E a \in Agents, f \in Files:
        AcquireLock(a, f) \/ ReleaseLock(a, f)
    \/ \E a \in Agents, t \in Tasks:
        ClaimTask(a, t) \/ CompleteTask(a, t)
    \/ \E t \in Tasks:
        ExpireClaim(t)

Spec == Init /\ [][Next]_<<locks, taskOwner, taskStatus>>

LockExclusivity ==
    \A f \in Files: locks[f] = NULL \/ locks[f] \in Agents

TaskClaimUniqueness ==
    \A t \in Tasks:
        taskStatus[t] = "claimed" => taskOwner[t] # NULL

CompletionOwnership ==
    \A t \in Tasks:
        taskStatus[t] = "completed" => taskOwner[t] # NULL

EventuallyReclaimable ==
    \A t \in Tasks:
        taskStatus[t] = "claimed" ~> taskStatus[t] = "pending" \/ taskStatus[t] = "completed"

=============================================================================
