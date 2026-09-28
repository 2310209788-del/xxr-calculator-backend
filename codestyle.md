# Coding Style

This project follows [PEP 8](https://peps.python.org/pep-0008/). Module, class, function naming, and exception handling follow this style guide.

- Use four spaces for indentation and avoid unclear abbreviations.
- Add documentation to public modules, classes, and important functions.
- Use parameterized SQL. Do not concatenate user input into SQL.
- Do not use `eval`, `exec`, or any mechanism that executes user expressions.
- Return JSON error responses with appropriate HTTP status codes.
