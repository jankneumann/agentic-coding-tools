# Contract inventory

dg-03 changes one in-process Python contract and introduces no HTTP, database, event, or
deployment API. The contract is `IsolationPosture(filesystem: bool, network: bool)` on
`EnvironmentProfile.posture`; `isolation_provided` remains a compatibility surface.
