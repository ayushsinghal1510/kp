User Task: {prompt}
Result: {result}

Write a summary answering the user's task using the result above. Start with 'SUCCESS:' or 'RETRY:'.

Formatting rules for the text after 'SUCCESS:' / 'RETRY:' (it is rendered directly as Markdown to the user in a chat UI):
- If the user asked to name/list/show the items ("name them", "list all", "what are they", etc.), list EVERY item from Result as a Markdown bullet list — one bullet per item, verbatim from the data. Never truncate to "representative" examples and never replace the full list with a paraphrased summary. This applies even for a few dozen items — only skip listing everything if Result contains more than ~50 rows, and in that case say explicitly "showing first 50 of N" (N must equal the real row count).
- If the user asked a count/aggregate question ("how many...", "what's the total...", "average price..."): answer the question in a direct sentence first. Then, if Result contains 10 or fewer items, also list them all as a Markdown bullet list right after (the user gets the count AND the data in one go). If Result has more than 10 items, stop at the sentence — don't list them unless asked.
- Only use a table (with a header row) when each item has multiple fields to show (e.g. name + price + supplier). For a flat list of names, use a bullet list, not a single-column table with an invented header.
- The number you state as the count MUST equal the number of bullets/rows you actually list — never state a different total than what you show. Do not invent groupings, brand commentary, or any text not literally derivable from Result.
- Use **bold** only for key figures (totals, prices, counts) — do not add a trailing summary sentence after a full list.
- Do not wrap the list or table in a code block.
- Keep it factual and grounded only in the result shown above; do not invent data, and do not leave a sentence unfinished.