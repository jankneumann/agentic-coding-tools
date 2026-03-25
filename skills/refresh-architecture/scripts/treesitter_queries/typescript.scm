; TypeScript pattern queries for tree-sitter enrichment
; Capture naming convention: @category.detail

; --- Error handling patterns ---

; Any catch clause
(catch_clause) @catch.any

; Catch with a parameter (typed or untyped)
(catch_clause
  parameter: (identifier) @catch.param)

; --- Dynamic imports ---

; Dynamic import() expressions
(call_expression
  function: (import) @import.dynamic)

; --- Comments ---

(comment) @comment.any
