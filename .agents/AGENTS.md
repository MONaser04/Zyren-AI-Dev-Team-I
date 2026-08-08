# STRICT FILE SIZE AND WRITE CONSTRAINTS

## 1. Absolute 150-Line Limit per File/Tool Call
- **CRITICAL RULE:** You are strictly FORBIDDEN from writing, modifying, or outputting any code block or single file that exceeds 150 lines of code in a single tool call (such as `write_to_file` or `replace_in_file`).
- If a file requires more than 150 lines, you MUST split the implementation into smaller, modular, highly decoupled helper files (e.g., helpers, sub-components, utility modules) of under 100 lines each.
- Under no circumstances should you output a single block containing over 150 lines of code.

## 2. Multi-Step Incremental Writing (Chunking Strategy)
- If a single monolithic file is absolutely required by the user and cannot be split into separate files, you must use this chunking strategy:
  1. Write only the skeleton/stubs of the file first (must be under 80 lines) using `write_to_file` with clear placeholder comments (e.g., `# TODO: Implement logic here`).
  2. Implement each placeholder/TODO incrementally one-by-one in subsequent messages using `replace_in_file`.
  3. Each incremental modification/edit MUST contain less than 80 lines of code.
- If you are about to write code that exceeds 150 lines, you MUST STOP immediately, explain the chunking plan to the user, and ask for permission to proceed with Step 1.

## 3. Tool Constraints
- NEVER rewrite an entire file using `write_to_file` if it is already established. Always prefer `replace_in_file` for targeted block edits.