Create a flat list of each actions you find in this webpage accessibility tree. For each action, describe it a short natural language description, keep it's identifier, and group them in different categories that make sense. The objective is that someone could read your list and immediately get what actions are possibly executable on that webpage.

{{{context}}}

The format should instead be a sort of markdown like:

# category-section-title
* ID: Short description

This could be something like:

# Cookie Consent Actions
* L1: Reveal cookie settings details (show cookies details link)
* B1: Reject all cookies (deny button)

Your final answer should be inserted into a <action-listing/> tag:

<action-listing>
your-answer-here
</action-listing>

Important notes:
- Output nothing else than the <action-listing/> tag with your answer inside.
- Every single interaction node should be listed in your output (All of them!)
- The actions should be ordered by relevance of category.
- You should avoid any duplicates at all costs.
