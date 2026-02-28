; Python pattern queries for tree-sitter enrichment
; Capture naming convention: @category.detail

; --- Exception handling patterns ---

; Bare except (no exception type specified)
(except_clause) @except.bare
(#not-has-child? @except.bare identifier)

; Broad except (catches Exception base class)
(except_clause
  (identifier) @except.broad_type)
(#eq? @except.broad_type "Exception")

; Any except clause (for counting)
(except_clause) @except.any

; --- Context managers ---

(with_statement) @context_manager.usage

; --- Type hints ---

; Function with return type annotation
(function_definition
  name: (identifier) @type_hint.function_name
  return_type: (type) @type_hint.return_type)

; Typed parameter
(typed_parameter
  (identifier) @type_hint.param_name
  type: (type) @type_hint.param_type)

; --- Assertions in production code ---

(assert_statement) @assertion.usage

; --- Comments ---

(comment) @comment.any
