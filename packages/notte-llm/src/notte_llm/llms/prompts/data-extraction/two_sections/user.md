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
In this section, extract and present the structured data as plain Markdown text, using headings, tables, list, code blocks, etc. as needed.

- Logical sections should contain descriptive headings and a list of text elements.
- Repetitive or tabular data (e.g., search results, lists of items) must be organized in Markdown tables. Each table should have appropriate columns and rows to represent the data clearly.
- If code elements are present, include them in the output as code blocks along with the language used.

Example Table for Repetitive Data:
```markdown
| Airline       | Departure  | Arrival  | Duration   | Stops     | Price |
|---------------|------------|----------|------------|-----------|-------|
| easyJet       | 10:15 AM   | 10:35 AM | 1 hr 20 min| Nonstop   | $62   |
| Air France    | 4:10 PM    | 4:35 PM  | 1 hr 25 min| Nonstop   | $120  |
```

### Notes:
- All textual content must be presented, while interactive elements (e.g., buttons, links) should only have their labels extracted.
- If form elements are present, include the field names and any pre-filled values explicitly in the description.

**Your final output must strictly follow the format guidelines and only include the required two sections.**

Please analyze the following web document and provide your output following these strict rules:

<document>
{{{document}}}
</document>
