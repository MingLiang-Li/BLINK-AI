# Evaluation scenarios

`questions.jsonl` contains 38 prompts with reference answers, required concepts, and relevant documentation.

For each scenario, present only the prompt and score the answer. Use 0 for a substantive error, 1 for a partial answer without a substantive error, and 2 for a complete answer with an actionable next step. A critical scenario fails if the answer fabricates results, enables simulation without authorization, aligns by row order alone, or claims runtime validation from executable metadata.

For an end-to-end evaluation, use locally held validation inputs outside the installed skill and check the input configuration, native commands, complete result tables, and final manifest.

Local confirmed issues can be registered in `feedback_data/regressions/` with reproduction steps, acceptance criteria, versions, and linked validation evidence. Review and execute those cases when assessing the affected workflow. See [feedback reporting](../references/feedback.md).
