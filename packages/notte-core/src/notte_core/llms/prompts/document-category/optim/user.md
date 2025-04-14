You are an expert web content analyst tasked with classifying webpages into specific categories based on their content and functionality. Your goal is to accurately categorize each webpage using the information provided.

Here is the webpage information you need to analyze:

<webpage_info>
{{document}}
</webpage_info>

Your task is to classify this webpage into one of the following categories (by priority):

1. "manage-cookies": Pages for managing cookies, usually in a modal/dialog asking for user action.
2. "overlay": Pages with a modal/dialog that is not a cookie management dialog.
3. "auth": Sign-in or sign-up pages, including modals asking users to sign up to continue.
4. "search-results": Pages displaying multiple items as results of a previous search query.
5. "data-feed": Pages displaying data in a grid/sequence (e.g., blog posts, news articles, social media feeds).
6. "item": Information pages about a particular item, typically accessed from search results or data feeds (e.g., product pages, news articles, social media posts, recipes).
7. "captcha": Pages asking users to resolve a CAPTCHA before continuing.
8. "payment": Pages where users input credit card or delivery information.
9. "form": Pages asking for user input, including contact forms (excluding auth forms).
10. "homepage": the homepage of the website (if it is not one of the other categories)
11. "other": Use this if the page doesn't fit any of the above categories.

Instructions:
1. Carefully analyze the webpage information provided.
2. Consider the primary function and content of the page.
3. If you're hesitating between two categories because the page fits both categories, return the first category in the list (i.e. "manage-cookies" has the highest priority and "other" has the lowest priority)
4. Wrap your analysis in <webpage_classification_analysis> tags, including arguments for and against each potentially applicable category, backup up by quotes from the webpage information. This anlysis should be consise.
5. Provide your final classification in <document-category> tags.

Here's an example of how your response should be structured:

<webpage_classification_analysis>
[Your detailed analysis of the webpage, including quotes, arguments, and summary]
</webpage_classification_analysis>

<document-category>[Your final classification]</document-category>

Please proceed with your analysis and classification of the given webpage.
