User Task: {prompt}
Result: {result}

Write a summary answering the user's task using the result above. Start with 'SUCCESS:' or 'RETRY:'.

Formatting rules for the text after 'SUCCESS:' / 'RETRY:' (it is rendered directly as Markdown to the user in a chat UI):
- If the result contains multiple rows/records or several fields per item, present them as a Markdown table with a header row, instead of a plain sentence or list.
- If the result is a single value or short fact, answer in 1-2 concise sentences — no table needed.
- Use **bold** for key figures (totals, prices, counts) and bullet points for short lists of 3+ items.
- Do not wrap the table or text in a code block.
- Keep it factual and grounded only in the result shown above; do not invent data.