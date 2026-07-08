User Task: {prompt}
Result: {result}

Write a summary answering the user's task using the result above. Start with 'SUCCESS:' or 'RETRY:'.

Formatting rules for the text after 'SUCCESS:' / 'RETRY:' (it is rendered directly as Markdown to the user in a chat UI):
- SHORT answer (a single value, or a list of items that is small enough to read at a glance): list the item(s) directly — a plain sentence for one value, or a Markdown bullet list for several. Do not pad it with extra sentences.
- LONG answer (many rows, or many fields per row): do not dump every row. Summarize — give the total count and any obvious grouping/pattern, then show at most a handful of representative rows as a Markdown table if a table genuinely helps.
- Only use a table when the result has multiple fields per item. For a flat list of names/values, use a bullet list, not a single-column table with an invented header.
- Never invent column headers, categories, or commentary (e.g. "key brands include") that aren't literally present in the result above — only report what's actually in Result.
- Use **bold** for key figures (totals, prices, counts).
- Do not wrap the table or text in a code block.
- Keep it factual and grounded only in the result shown above; do not invent data, and do not leave a sentence unfinished.