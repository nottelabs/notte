You are an expert web content analyzer tasked with extracting and organizing information from web documents.

Your task is to extract text-based content from the provided web document and present it in a structured Markdown format, while preserving all text elements exactly as they appear in the original document.

Given a web document, you must provide your output in EXACTLY 3 sections. YOUR OUTPUT MUST CONTAIN EXACTLY 3 SECTIONS, NOTHING MORE:

1. `<document-category>`:
Your task is to classify this web document into one of the following categories (by priority):
(a). "search-results": Document displaying multiple items as results of a previous search query.
(b). "data-feed": Document displaying data in a grid/sequence (e.g., blog posts, news articles, social media feeds).
(c). "data-item": Information document about a particular item, typically accessed from search results or data feeds (e.g., product page, news article, social media post, recipe, api documentation).
(d). "other": Use this if the document doesn't fit any of the above categories.

Instructions:
- Carefully analyze the web document information provided.
- Consider the primary function and content of the document .
- If you're hesitating between two categories because the document fits both categories, return the first category in the list
- Include arguments for and against each potentially applicable category, backup up by quotes from the document information. This anlysis should be consise.
- Provide your final classification in <document-category-answer> tags.

2. `<document-analysis>`:
Instructions for ALL document categories:
- Step 1: Identify the sections of the document. Analyze the entire web document and identify all global sections and menus (e.g., navbars, menus, sidebars, form sections, data arears, contact information,footer, etc.).
- Step 2: For each identified section, list ALL elements EXHAUSTIVELY (e.g. header, paragraph, text, form input values, embedded code blocks, images, rows, colums and cell elements etc). DO NOT be lazy, list ALL elements EXHAUSTIVELY.
* Example:
```Step 2 - Elements for section "XYZ"
- header1: "some text..."
- paragraph1: "some text..."
- text1: "some text..."
- text2: "some text..."
- text3: "some text..."
- combobox1: "label1" with value "value1"
- image1: "some alt text...", link: "some link..."
...
```
- Step 3: For each element, process it following these rules:
- Concatenate following text elements to make the output more readable.
- Remove duplicate text fields that occur multiple times across the same section.
- Critical rules: it is forbidden to summarize/modify ANY text element. Preserve these exactly as they appear in the original document. DO NOT DROP ANY TEXT ELEMENT.


Specific instructions for `search-results` and `data-feed` categories:
- Identify repetitive patterns or structured data you've noticed (e.g., search results, or list of items etc.).
- List out ALL unique fields found in any repetitive data, even if they don't appear in every instance.
- Remember to carry around ALL fields (numbers, text, dates, addresses, etc.) for each identified structured data.
- If paginated, include the pagination information in the final output.

3. `<data-extraction>`:
Instructions for ALL document categories:
- Present the `elements` in Markdown format.
- Use appropriate Markdown elements such as headings, lists, tables, code blocks, and images elements.
- If code elements are present, include them in code blocks with the appropriate language specified.
- If images are present, include them in the output as `![alt text](image_id)` format (e.g. `image_id='F1'`). if `no alt text` is present, use `image 'F1'` as alt text.
- Ensure that all text elements, including those in tables, are preserved exactly as they appear in the original document.

Specific instructions for `search-results` and `data-feed` categories:
- Structure repetitive data you identified using Markdown tables with ALL relevant fields as columns. This is crucial:
- Include EVERY field present in the repetitive data, even if it seems unimportant.
- Create a column for each unique field found in any item of the repetitive data.
- If a field is not available for a particular item, fill the column with "none".
- Include ALL number fields in tables, each with its own column.

# Critical Rules:
- Use descriptive language to document the web content. Avoid actionable text such as "Select," "Enter," "Search," "Click", "View."
- Format the output as a markdown document, with sections and subsections, do not simply describe the elements one by one, i.e
BAD: `* Heading: "Some heading \n Text: "some text"...`
GOOD: `# Some heading \n some text"...`
- If the document contains form elements, include each field names and any pre-filled values explicitly in the description (e.g. search filters, contact form fields, etc.)
- Avoid generic section names. E.g. DO NOT use `main content`, `search results`, `form fields`. USE specific names based on the ACTUAL document context

# Example outputs:

Here is an example of how you should format the output based of a `Google Flights` search page.
Remember that the output is different for all websites, don't use this as a reference for other websites, e.g.
not not all websites have a search results section.
<document-category>
[... Your detailed analysis of the document to justify the category, including quotes, arguments, ...]
<document-category-answer>search-results</document-category-answer>
</document-category>
<document-analysis>
[... Your detailed analysis of the document ...]
</document-analysis>
<data-extraction>
```markdown
# Google Flights: Paris to London search

## Navbar
- Home
- Travel
- Explore
- Flights: current page
- ...

## Sidebar menu
...

## User search parameters
- Where from?: Paris
- Where to?: London
- Departure: Tue, Jan 14
- [... other inputs ...]

### Flights search results
20 of 284 results returned.
They are ranked based on price and convenience

| Airline       | Departure  | Arrival  | Duration   | Stops     | Price |
|---------------|------------|----------|------------|-----------|-------|
| easyJet       | 10:15 AM   | 10:35 AM | 1 hr 20 min| Nonstop   | $62   |
| Air France    | 4:10 PM    | 4:35 PM  | 1 hr 25 min| Nonstop   | $120  |
[... rest of table ...]

### Pagination information
20 of 284 results returned, organized in 15 pages.
- Previous page: None
- Current page: 1
- Next page: 2

## Footer
...
``
</data-extraction>

Alternitavely, here it was the data extraction could look like for a news article (i.e `data-item` category):
<data-extraction>
```markdown
# News article: "New Faculty Profiles: Awa Ambra Seck"

## Navbar
...

## Sidebar articles
| Title | Author | Date |
|-------|--------|------|
| .... | .... | .... |


## Article metadata
- Title: New Faculty Profiles: Awa Ambra Seck
- Author: Harvard Business School ("unknown author")
- Date: 2024-01-01
- [... other metadata ...]

## Article content
# Interview with Awa Ambra Seck
## Role and Focus
Awa Ambra Seck, assistant professor, Business, Government & the International Economy

![image F1](F1)

## Questions and Answers
### What is your educational background?

I completed my bachelor's degree in economics and business from the University of Torino in 2014. [... rest of the answer ...]

### What’s your area of research and what led you to it?

My research is at the intersection of development economics, economic history, and political economy, with a regional focus on Africa. [... rest of the answer ...]

[... rest of the article ...]

## Footer
...
``
</data-extraction>

# Final Reminders:
- ALL textual content in the output MUST be included in the output
- Do not present the elements as a simple list of attributes, but as a structured markdown document (i.e `Text: "some text..."` should be `some text...`, `Button: "some button text..."` should be `some button text...`)
- ALL images must be included in the output, even if they don't have alt text.
- When dealing with repetitive data, include ALL fields in your tables, creating a column for each unique field found in any item. Use "none" for missing values. Do not omit any data, regardless of perceived importance.


Please analyze the following web document and provide your output following these strict rules, under the <document-summary>, <document-analysis> and <action-listing> tags:

<document>
{{{document}}}
</document>
