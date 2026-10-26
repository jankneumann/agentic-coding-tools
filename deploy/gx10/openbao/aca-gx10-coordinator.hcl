# Read-only AppRole policy for the coordinator's secret renderer. It reads its
# own path and nothing of the analyzer's: sharing one OpenBao does not mean
# sharing one secret path.
path "secret/data/coordinator/gx10/runtime" {
  capabilities = ["read"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
