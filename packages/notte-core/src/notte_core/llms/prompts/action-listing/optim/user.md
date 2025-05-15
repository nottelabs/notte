You are an expert in analyzing web documents to create comprehensive documentation of user interactions.

Given a web document, you must provide your output in EXACTLY 3 sections. YOUR OUTPUT MUST CONTAIN EXACTLY 3 SECTIONS, NOTHING MORE:

1. <document-summary>
Inside this section, provide a 2-3 sentence summary of the content of the document and what users are expected to perform on it. Focus on the main content and intent. Avoid navbar and footer elements.
Use descriptive and concise language.

2. <document-analysis>
Inside this section, show your analytical work:
- Count of all terminal nodes by type (B, L, I, O, M)
- Verification that each ID appears exactly once in the document
- Discussion of how you identified parameters
- Discussion of your categorization strategy
- Explanation of how you grouped similar functionalities
- Final count verification
- Explain your reasoning for the preparation of the table
This section should contain all your reasoning and analysis steps.
For each section above, start with a new line and a new paragraph with #.

3. <action-listing>
Inside this section, provide the final table in this exact markdown format:
| ID | Description | Parameters | Category |
[Table contents following rules below]
Nothing else should appear in this section except the table.

# Rules for creating the table:

1. ID Column:
- Each ID must appear exactly once
- NO GROUPING OF IDs (e.g., "L8-L27" is FORBIDDEN)
- IDs must match exactly as they appear in the document (B1, L1, I1, O1, M1, etc.)

2. Description Column:
- Must be concise and self-explanatory without seeing the interface
- Should clearly state what action/functionality the element provides
- Include current state/value where applicable
- Should be understandable in isolation
- Ideally, start with an action verb (Select, Enter, Search, View, etc.)
BAD: "New York to London"
GOOD: "Show flights from New York to London"
BAD: "Enable to subscribe"
GOOD: "Subscribe to the newsletter to get updates"
- Descriptions should be unique for each action, don't repeat the same description for different actions.
BAD: "Show the details of the recipe", "Show the details of the recipe"
GOOD: "Show the details of the 'Kim's Lasagna' recipe", "Show the details of the 'Classic Lasagna' recipe"

3. Parameters Column:
- For elements with ID starting with 'I': document all parameters
- Format: name: parameterName: type: parameterType, default="default_value", values=["value1", "value2", ...]
- Example: name: destination: type: str, default="New York", values=["New York", "London", "Paris"]
- Default value should only be included if there is an explicit default value in the document
- Values represent what this parameter can take. They should be included if there is an explicit list of possible values in the document. Let this be empty if there is no list of possible values.
- Types should be: str, number, date, boolean
- For non-input elements, leave the Parameters column empty
- Parameter names should be as descriptive as possible and understandable without context
- Parameter names should be camelCase

4. Category Column:
- Group similar actions into logical categories
- Use clear, descriptive category names
- Common categories include but are not limited to:
  * Navigation (site navigation, major sections)
  * Search & Input (core search functionality)
  * Settings & Preferences
  * User Account
  * Help & Support
  * Discovery & Exploration
  * Legal & Policy
  * Newsletter
- Each action must be assigned to exactly one category
- Categories should be consistent across similar actions
- Category names should be clear to users who can't see the page

# Critical Rules:
- Every ID must have exactly one entry
- No grouping of IDs allowed (e.g., no "L10-L20")
- Button and Link elements should almost always have "None" for parameters
- Descriptions must be complete sentences that clearly describe the action
- Default values must be documented when present in the source
- Categories must be logically coherent and user-focused
- Be complete: list all actions of the document inside the table, don't miss any or use ellipsis (...)

Example of CORRECT entries:
| ID | Description | Type | Parameters | Category |
| B1 | Open the main navigation menu | Button | | Navigation |
| I1 | Allow user to select trip type | Combobox | name: tripType: type: str, default="round-trip", values=["round-trip", "one-way", "multi-city"] | Flight Search |
| O1 | Select the "round-trip" option | Option | | Flight Search |
| L1 | Open the home page | Link | | Navigation |

Example of INCORRECT entries:
| ID | Description | Type | Parameters | Category |
❌ | L8-L27 | Show popular destinations | Link | None | Navigation |
❌ | B1 | Main menu | Button | None | Nav |
❌ | I1 | Trip type | Combobox | type: string | Search |
❌ | ... | ... | ... | ... |

# Example output:

<document-summary>
This is XYZ homepage interface, focused on flight search and discovery. Users can search for specific flights by entering origin/destination and dates, while also exploring ...
[More description...]
</document-summary>
<document-analysis>
Found 30 button elements (B1-B30), 55 link elements (L1-L55), and 6 input elements (I1-I6).
Verified that each ID appears exactly once.
Identified parameters for input elements I1-I6.
Grouped actions into 8 main categories based on functionality...
[Additional analysis...]
</document-analysis>
<action-listing>
```markdown
| ID | Description | Parameters | Category |
|-----|------------|------------|-----------|
| I1 | Selects trip type (round-trip, one-way, or multi-city) | name: tripType: type: str, default="round-trip", values=["round-trip", "one-way", "multi-city"] | Flight Search |
[Rest of table...]
```
</action-listing>

Please analyze the following web document and provide your output following these strict rules.
CRITICAL: DO NOT USE "# Step 1: Document Summary.... # Step 2: Document Analysis.... # Step 3: Action Listing..."
CRITICAL: structure your output as: <document-summary>...</document-summary>, <document-analysis>...</document-analysis> and <action-listing>...</action-listing> tags:

Your turn:

<document>
{{{document}}}
</document>
