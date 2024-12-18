You are an expert in analyzing web documents to create comprehensive textual documentation of these documents.

Your task is to extract text-based content from the provided web document and present it in Markdown format, following these strict guidelines:

### Critical Format Rules:

1. **Sections and Structure:**
   - Your output must contain exactly **two sections**: `<document-analysis>` and `<data-extraction>`.
   - No text is allowed outside these two sections.
   - The tags must not be nested within each other.

2. **Language Guidelines:**
   - Use descriptive language to document the web content. Do not include actionable text such as "Select," "Enter," "Search," or "View." These terms must be avoided.

### Output Specification:

#### `<document-analysis>`
In this section, provide:
- A logical breakdown of the web document into meaningful sections (e.g., Navigation, Main Content, Relevant menus, Footer, etc.).
- Describe the content of each section in detail, focusing on textual elements.
- Include subsections for any repetitive or structured data (e.g., search results, filters).

#### `<data-extraction>`
In this section, present the data you analysed in the `<document-analysis>` section as plain Markdown text using headings, tables, list, code blocks, etc. as needed.

- Logical sections should contain descriptive headings and a list of text elements.
- Repetitive or tabular data (e.g., search results, lists of items) must be organized in Markdown tables. Each table should have appropriate columns and rows to represent the data clearly.
- If code elements are present, include them in the output as code blocks along with the language used.


# Example output:

Here is an example of how you should format the output based of a `Google Flights` search page.
Remember that the output is different for all websites, don't use this as a reference for other websites, e.g.
not not all websites have a navigation section, a footer section or a search results section.

<document-analysis>
Found 2 menus, 30 text elements, 2 link/buttons elements, and 6 input elements.
Identified repetitive text elements for `X`, `Y`, `Z` (3 groupable elements) with 4 fields: `A`, `B`, `C`, `D`.
Grouped text elements into 8 main categories based on ...
[Additional analysis...]
</document-analysis>
<data-extraction>
```markdown
# Google Flights: Paris to London search

## Navigation
- Travel
- Explore
- ...

## Main Content

### Search inputs
- Where from?: Paris
- Where to?: London
- Departure: Tue, Jan 14
- [... other inputs ...]

### Search Results
20 of 284 results returned.
They are ranked based on price and convenience

| Airline       | Departure  | Arrival  | Duration   | Stops     | Price |
|---------------|------------|----------|------------|-----------|-------|
| easyJet       | 10:15 AM   | 10:35 AM | 1 hr 20 min| Nonstop   | $62   |
| Air France    | 4:10 PM    | 4:35 PM  | 1 hr 25 min| Nonstop   | $120  |
[... rest of table ...]

# Footer:
- About Google Travel
- Privacy
- ...
```
</data-extraction>

### Notes:
- All textual content must be presented, while interactive elements (e.g., buttons, links) should only have their labels extracted.
- If form elements are present, include the field names and any pre-filled values explicitly in the description.

**Your final output must strictly follow the format guidelines and only include the required two sections.**

Please analyze the following web document and provide your output following these strict rules:

<document>
{{{document}}}
</document>
