; Cross-language security pattern queries for tree-sitter enrichment
; These queries work on Python source files
; Capture naming convention: @security.detail

; --- eval/exec usage ---

; eval() calls
(call
  function: (identifier) @security.eval_exec)
(#match? @security.eval_exec "^(eval|exec)$")

; --- Hardcoded secrets patterns ---

; String assignments that look like secrets (API keys, passwords, tokens)
; Matches: SECRET = "..." / password = "..." / api_key = "..."
(assignment
  left: (identifier) @security.secret_var_name
  right: (string) @security.secret_value)
(#match? @security.secret_var_name "(?i)(secret|password|token|api_key|apikey|private_key)")
